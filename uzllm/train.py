import argparse
import json
import math
import os
import time
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP

from uzllm.model import CONFIGS, GPT, GPTConfig


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="base", choices=list(CONFIGS))
    ap.add_argument("--data", required=True, help="tokenize_corpus.py chiqargan papka")
    ap.add_argument("--out", default="checkpoints")
    ap.add_argument("--tokenizer", default=None, help="namunalar chiqarish uchun")
    ap.add_argument("--mix", default="uz=0.65,en=0.35", help="tillar nisbati")
    ap.add_argument("--micro-batch", type=int, default=16, help="bir GPU, bir qadamdagi ketma-ketliklar")
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--context-len", type=int, default=None)
    ap.add_argument("--total-tokens", type=float, default=3e9)
    ap.add_argument("--lr", type=float, default=6e-4)
    ap.add_argument("--min-lr-ratio", type=float, default=0.1)
    ap.add_argument("--warmup-steps", type=int, default=700)
    ap.add_argument("--weight-decay", type=float, default=0.1)
    ap.add_argument("--grad-clip", type=float, default=1.0)
    ap.add_argument("--eval-interval", type=int, default=250)
    ap.add_argument("--eval-batches", type=int, default=20)
    ap.add_argument("--log-interval", type=int, default=10)
    ap.add_argument("--save-interval", type=int, default=250)
    ap.add_argument("--time-limit-hours", type=float, default=11.3)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--dtype", default="auto", choices=["auto", "float32", "float16", "bfloat16"])
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--seed", type=int, default=1337)
    return ap.parse_args()


SAMPLE_PROMPTS = [
    "Oʻzbekiston poytaxti",
    "Amir Temur",
    "Sogʻlom boʻlish uchun har kuni",
    "The capital of France is",
]


class MixedLoader:

    def __init__(self, data_dir: Path, split: str, mix: dict[str, float], ctx: int, seed: int):
        self.ctx = ctx
        self.data = {}
        for lang in mix:
            p = data_dir / f"{lang}_{split}.bin"
            if p.exists() and p.stat().st_size > 2 * (ctx + 1):
                self.data[lang] = np.memmap(p, dtype=np.uint16, mode="r")
        assert self.data, f"{data_dir} da {split} ma'lumot topilmadi"
        langs = list(self.data)
        w = np.array([mix[l] for l in langs], dtype=np.float64)
        self.langs, self.weights = langs, w / w.sum()
        self.rng = np.random.default_rng(seed)

    def batch(self, bs: int, lang: str | None = None):
        xs, ys = [], []
        for _ in range(bs):
            l = lang or self.rng.choice(self.langs, p=self.weights)
            d = self.data[l]
            i = self.rng.integers(0, len(d) - self.ctx - 1)
            chunk = torch.from_numpy(d[i:i + self.ctx + 1].astype(np.int64))
            xs.append(chunk[:-1])
            ys.append(chunk[1:])
        return torch.stack(xs), torch.stack(ys)


def lr_at(step, max_steps, args):
    if step < args.warmup_steps:
        return args.lr * (step + 1) / args.warmup_steps
    progress = min(1.0, (step - args.warmup_steps) / max(1, max_steps - args.warmup_steps))
    min_lr = args.lr * args.min_lr_ratio
    return min_lr + 0.5 * (args.lr - min_lr) * (1 + math.cos(math.pi * progress))


def main():
    args = get_args()

    ddp = "RANK" in os.environ
    if ddp:
        dist.init_process_group("nccl")
        rank, local_rank, world = int(os.environ["RANK"]), int(os.environ["LOCAL_RANK"]), int(os.environ["WORLD_SIZE"])
        device = f"cuda:{local_rank}"
        torch.cuda.set_device(device)
    else:
        rank, local_rank, world = 0, 0, 1
        device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    master = rank == 0
    device_type = "cuda" if "cuda" in device else "cpu"
    torch.manual_seed(args.seed + rank)

    if args.dtype == "auto":
        if device_type == "cuda":
            major, _ = torch.cuda.get_device_capability()
            args.dtype = "bfloat16" if major >= 8 else "float16"
        else:
            args.dtype = "float32"
    ptdtype = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}[args.dtype]
    autocast = nullcontext() if device_type == "cpu" else torch.autocast(device_type, dtype=ptdtype)
    scaler = torch.amp.GradScaler(device_type, enabled=(args.dtype == "float16"))
    if device_type == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    data_dir = Path(args.data)
    meta = json.loads((data_dir / "meta.json").read_text())
    cfg_dict = dict(CONFIGS[args.config].__dict__)
    cfg_dict["vocab_size"] = meta["vocab_size"]
    if args.context_len:
        cfg_dict["context_len"] = args.context_len
    cfg = GPTConfig(**cfg_dict)

    out = Path(args.out)
    ckpt_path = out / "last.pt"
    step, best_val = 0, float("inf")
    model = GPT(cfg).to(device)
    optimizer = model.configure_optimizer(args.lr, args.weight_decay, device_type=device_type)

    if args.resume and ckpt_path.exists():
        ck = torch.load(ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        optimizer.load_state_dict(ck["optimizer"])
        if "scaler" in ck:
            scaler.load_state_dict(ck["scaler"])
        step, best_val = ck["step"], ck.get("best_val", best_val)
        if master:
            print(f"Davom ettirilmoqda: {step}-qadamdan")

    raw_model = model
    if args.compile:
        model = torch.compile(model)
    if ddp:
        model = DDP(model, device_ids=[local_rank])

    mix = {k: float(v) for k, v in (p.split("=") for p in args.mix.split(","))}
    train_loader = MixedLoader(data_dir, "train", mix, cfg.context_len, args.seed + rank + step)
    val_loader = MixedLoader(data_dir, "val", mix, cfg.context_len, 999)

    tokens_per_step = args.micro_batch * args.grad_accum * cfg.context_len * world
    max_steps = max(1, int(args.total_tokens // tokens_per_step))
    if master:
        out.mkdir(parents=True, exist_ok=True)
        print(f"Model: {args.config}, {raw_model.num_params() / 1e6:.1f}M parametr | qurilma: {device} x{world}, {args.dtype}")
        print(f"Har qadamda {tokens_per_step:,} token | jami {max_steps:,} qadam | ~{args.total_tokens / 1e9:.2f} mlrd token")
        print(f"Tillar nisbati: {dict(zip(train_loader.langs, train_loader.weights.round(2)))}")

    tokenizer = None
    if master and args.tokenizer:
        from uzllm.tokenizer import load_tokenizer
        tokenizer = load_tokenizer(args.tokenizer)

    @torch.no_grad()
    def evaluate():
        model.eval()
        res = {}
        for lang in val_loader.langs:
            losses = []
            for _ in range(args.eval_batches):
                x, y = val_loader.batch(args.micro_batch, lang)
                with autocast:
                    _, loss = raw_model(x.to(device), y.to(device))
                losses.append(loss.item())
            res[lang] = float(np.mean(losses))
        model.train()
        return res

    @torch.no_grad()
    def samples():
        if tokenizer is None:
            return
        raw_model.eval()
        for p in SAMPLE_PROMPTS:
            ids = torch.tensor([tokenizer.encode(p).ids], device=device)
            with autocast:
                outp = raw_model.generate(ids, max_new_tokens=40, temperature=0.8)
            print(f"   > {tokenizer.decode(outp[0].tolist())!r}")
        raw_model.train()

    def save(name="last.pt", full=True):
        ck = {"model": raw_model.state_dict(), "step": step, "best_val": best_val,
              "config": cfg.__dict__, "args": vars(args)}
        if full:
            ck["optimizer"] = optimizer.state_dict()
            ck["scaler"] = scaler.state_dict()
        tmp = out / (name + ".tmp")
        torch.save(ck, tmp)
        os.replace(tmp, out / name)
        (out / (name.replace(".pt", ".json"))).write_text(json.dumps({"step": step, "best_val": best_val}))

    t_start = time.time()
    t_last = time.time()
    log_file = open(out / "train_log.jsonl", "a") if master else None
    model.train()
    while step < max_steps:
        lr = lr_at(step, max_steps, args)
        for g in optimizer.param_groups:
            g["lr"] = lr

        loss_acc = 0.0
        for micro in range(args.grad_accum):
            x, y = train_loader.batch(args.micro_batch)
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            sync = nullcontext()
            if ddp and micro < args.grad_accum - 1:
                sync = model.no_sync()
            with sync, autocast:
                _, loss = model(x, y)
                loss = loss / args.grad_accum
            scaler.scale(loss).backward()
            loss_acc += loss.item()

        scaler.unscale_(optimizer)
        gnorm = torch.nn.utils.clip_grad_norm_(raw_model.parameters(), args.grad_clip)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)
        step += 1

        if master and step % args.log_interval == 0:
            dt = time.time() - t_last
            t_last = time.time()
            tps = tokens_per_step * args.log_interval / dt
            eta_h = (max_steps - step) * tokens_per_step / tps / 3600
            print(f"qadam {step:6d}/{max_steps} | loss {loss_acc:.3f} | lr {lr:.2e} | norm {gnorm:.2f} | "
                  f"{tps / 1e3:.1f}k tok/s | qolgan ~{eta_h:.1f} soat", flush=True)
            log_file.write(json.dumps({"step": step, "loss": loss_acc, "lr": lr, "tok_s": tps}) + "\n")
            log_file.flush()

        if step % args.eval_interval == 0 or step == max_steps:
            if master:
                v = evaluate()
                vmean = float(np.mean(list(v.values())))
                print(f"== TEKSHIRUV qadam {step}: " + ", ".join(f"{k}={l:.3f}" for k, l in v.items()), flush=True)
                log_file.write(json.dumps({"step": step, "val": v}) + "\n")
                samples()
                if vmean < best_val:
                    best_val = vmean
                    save("best.pt", full=False)

        if master and (step % args.save_interval == 0 or step == max_steps):
            save()

        stop = torch.tensor(float(time.time() - t_start > args.time_limit_hours * 3600), device=device)
        if ddp:
            dist.all_reduce(stop, op=dist.ReduceOp.MAX)
        if stop.item() > 0:
            if master:
                save()
                print(f"Vaqt chegarasi: {step}-qadamda saqlandi. Keyingi sessiyada --resume bilan davom eting.")
            break

    if master:
        print("O'qitish tugadi." if step >= max_steps else "To'xtatildi.")
        log_file.close()
    if ddp:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
