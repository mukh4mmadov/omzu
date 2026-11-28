import argparse
import json
import math
import os
import random
import time
from contextlib import nullcontext
from pathlib import Path

import torch
import torch.distributed as dist
import torch.nn.functional as F
from torch.nn.parallel import DistributedDataParallel as DDP

from uzllm.chat_format import encode_dialog
from uzllm.model import GPT, GPTConfig
from uzllm.tokenizer import load_tokenizer


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", required=True, help="pretraining checkpoint")
    ap.add_argument("--data", required=True, help="train.jsonl va val.jsonl joylashgan papka")
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--out", default="checkpoints/chat")
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch-tokens", type=int, default=16384, help="bir GPU, bir micro-batch dagi tokenlar")
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--warmup-steps", type=int, default=100)
    ap.add_argument("--weight-decay", type=float, default=0.05)
    ap.add_argument("--eval-interval", type=int, default=200)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--time-limit-hours", type=float, default=11.0)
    return ap.parse_args()


def load_split(path: Path, tok, max_len: int):
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            enc = encode_dialog(tok, json.loads(line)["messages"], max_len)
            if enc:
                items.append(enc)
    return items


def make_batches(items, batch_tokens: int, shuffle: bool, seed: int):
    order = sorted(range(len(items)), key=lambda i: len(items[i][0]))
    batches, cur, cur_max = [], [], 0
    for i in order:
        L = len(items[i][0])
        if cur and max(cur_max, L) * (len(cur) + 1) > batch_tokens:
            batches.append(cur)
            cur, cur_max = [], 0
        cur.append(i)
        cur_max = max(cur_max, L)
    if cur:
        batches.append(cur)
    if shuffle:
        random.Random(seed).shuffle(batches)
    return batches


def collate(items, idxs, pad_id: int, device):
    L = max(len(items[i][0]) for i in idxs)
    x = torch.full((len(idxs), L), pad_id, dtype=torch.long)
    y = torch.full((len(idxs), L), -1, dtype=torch.long)
    for r, i in enumerate(idxs):
        ids, labels = items[i]
        x[r, :len(ids)] = torch.tensor(ids)
        y[r, :len(ids) - 1] = torch.tensor(labels[1:])
    return x.to(device), y.to(device)


def main():
    args = get_args()
    ddp = "RANK" in os.environ
    if ddp:
        dist.init_process_group("nccl")
        rank, world = int(os.environ["RANK"]), int(os.environ["WORLD_SIZE"])
        device = f"cuda:{os.environ['LOCAL_RANK']}"
        torch.cuda.set_device(device)
    else:
        rank, world = 0, 1
        device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    master = rank == 0
    dtype = torch.float32
    if "cuda" in device:
        dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
    autocast = torch.autocast("cuda", dtype=dtype) if "cuda" in device else nullcontext()
    scaler = torch.amp.GradScaler("cuda", enabled=(dtype == torch.float16))

    tok = load_tokenizer(args.tokenizer)
    pad_id = tok.token_to_id("<|pad|>")
    ck = torch.load(args.init, map_location="cpu", weights_only=False)
    cfg = GPTConfig(**ck["config"])
    model = GPT(cfg)
    model.load_state_dict(ck["model"])
    model.to(device)
    raw = model
    if ddp:
        model = DDP(model, device_ids=[int(os.environ["LOCAL_RANK"])])

    data = Path(args.data)
    max_len = min(args.max_len, cfg.context_len)
    train = load_split(data / "train.jsonl", tok, max_len)
    val = load_split(data / "val.jsonl", tok, max_len)
    opt = raw.configure_optimizer(args.lr, args.weight_decay, device_type="cuda" if "cuda" in device else "cpu")

    batches_per_epoch = len(make_batches(train, args.batch_tokens, False, 0)) // world
    total_steps = max(1, int(batches_per_epoch * args.epochs / args.grad_accum))
    out = Path(args.out)
    if master:
        out.mkdir(parents=True, exist_ok=True)
        n_lab = sum(sum(1 for l in lab if l != -1) for _, lab in train)
        print(f"SFT: {len(train):,} misol ({n_lab / 1e6:.1f}M o'qitiladigan token), val {len(val):,} | "
              f"{total_steps} qadam | {raw.num_params() / 1e6:.0f}M parametr | {device} x{world}")

    @torch.no_grad()
    def evaluate():
        raw.eval()
        tot, n = 0.0, 0
        for idxs in make_batches(val, args.batch_tokens, False, 0)[:60]:
            x, y = collate(val, idxs, pad_id, device)
            with autocast:
                logits = raw.lm_head(raw.norm(_hidden(raw, x)))
            loss = F.cross_entropy(logits.float().view(-1, logits.size(-1)), y.view(-1), ignore_index=-1, reduction="sum")
            tot += loss.item()
            n += (y != -1).sum().item()
        raw.train()
        return tot / max(1, n)

    def save():
        torch.save({"model": raw.state_dict(), "config": cfg.__dict__, "step": step, "val": best}, out / "best.pt")

    step, best, t0 = 0, float("inf"), time.time()
    epoch = 0
    model.train()
    while step < total_steps:
        batches = make_batches(train, args.batch_tokens, True, seed=epoch)[rank::world]
        for bi in range(0, len(batches) - args.grad_accum + 1, args.grad_accum):
            lr = args.lr * min(1.0, (step + 1) / args.warmup_steps) * 0.5 * (1 + math.cos(math.pi * step / total_steps))
            for g in opt.param_groups:
                g["lr"] = lr
            tot_loss = 0.0
            for k in range(args.grad_accum):
                x, y = collate(train, batches[bi + k], pad_id, device)
                sync = model.no_sync() if ddp and k < args.grad_accum - 1 else nullcontext()
                with sync, autocast:
                    _, loss = model(x, y)
                    loss = loss / args.grad_accum
                scaler.scale(loss).backward()
                tot_loss += loss.item()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(raw.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            opt.zero_grad(set_to_none=True)
            step += 1
            if master and step % 20 == 0:
                print(f"qadam {step}/{total_steps} | loss {tot_loss:.3f} | lr {lr:.2e} | {(time.time() - t0) / 60:.1f} daq", flush=True)
            if master and (step % args.eval_interval == 0 or step == total_steps):
                v = evaluate()
                print(f"== TEKSHIRUV {step}: val loss {v:.3f}", flush=True)
                if v < best:
                    best = v
                    save()
            if step >= total_steps or time.time() - t0 > args.time_limit_hours * 3600:
                break
        epoch += 1
        if time.time() - t0 > args.time_limit_hours * 3600:
            break
    if master:
        if best == float("inf"):
            save()
        print("SFT tugadi. Eng yaxshi val loss:", best)
    if ddp:
        dist.destroy_process_group()


def _hidden(m: GPT, x):
    h = m.embed(x)
    T = x.size(1)
    cos, sin = m.rope_cos[:T].to(h.dtype), m.rope_sin[:T].to(h.dtype)
    for b in m.blocks:
        h = b(h, cos, sin)
    return h


if __name__ == "__main__":
    main()
