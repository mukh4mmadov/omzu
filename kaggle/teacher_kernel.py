import glob
import json
import os
import subprocess
import sys
import time
import traceback

T0 = time.time()
INPUT = "/kaggle/input"
WORK = "/kaggle/working"
JOB = os.environ.get("OMZU_JOB")


def find_one(pattern):
    hits = sorted(glob.glob(os.path.join(INPUT, "**", pattern), recursive=True))
    if not hits:
        sys.exit(f"Topilmadi: {pattern}")
    return hits[0]


cfg = globals().get("CFG") or json.load(open(find_one("teacher_config.json")))
SCRIPT = os.path.abspath(__file__)


def worker(job):
    os.environ["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
    prompts = [json.loads(line) for line in open(find_one("prompts.jsonl"), encoding="utf-8")]
    items = prompts[job["lo"]:job["hi"]][job["gpu"]::job["dp"]]
    model, tag = job["model"], job["tag"]
    out_path = os.path.join(WORK, f"out_{tag}.jsonl")
    st = {"tag": tag, "gpu": job["gpu"], "model": model, "backend": job["backend"], "planned": len(items)}
    try:
        from vllm import LLM, SamplingParams
        t = time.time()
        llm = LLM(model=model, tensor_parallel_size=1, dtype="half", quantization=cfg.get("quant"),
                  max_model_len=cfg.get("max_model_len", 3072), gpu_memory_utilization=cfg.get("gpu_util", 0.90),
                  max_num_seqs=cfg.get("max_num_seqs", 128), enforce_eager=cfg.get("eager", False))
        st["load_s"] = round(time.time() - t)
        tok = llm.get_tokenizer()
        sp = SamplingParams(temperature=0.7, top_p=0.8, top_k=20, max_tokens=cfg.get("max_tokens", 1100))
        done = gen_tokens = 0
        t = time.time()
        bs = cfg.get("batch", 256)
        with open(out_path, "a", encoding="utf-8") as f:
            for i in range(0, len(items), bs):
                if time.time() > job["deadline"]:
                    print(f"[{tag}] Vaqt tugadi — to'xtatildi.", flush=True)
                    break
                chunk = items[i:i + bs]
                texts = [tok.apply_chat_template(
                    [{"role": "system", "content": it["system"]}, {"role": "user", "content": it["prompt"]}],
                    tokenize=False, add_generation_prompt=True, enable_thinking=False) for it in chunk]
                outs = llm.generate(texts, sp, use_tqdm=False)
                for it, o in zip(chunk, outs):
                    c = o.outputs[0]
                    gen_tokens += len(c.token_ids)
                    f.write(json.dumps({"id": it["id"], "kind": it["kind"], "model": model, "text": c.text,
                                        "finish": c.finish_reason}, ensure_ascii=False) + "\n")
                f.flush()
                done += len(chunk)
                el = time.time() - t
                print(f"[{tag}] {done}/{len(items)}  {gen_tokens / el:.0f} tok/s  "
                      f"{done / el * 3600:.0f} topshiriq/soat  ({(time.time() - T0) / 3600:.2f} soat)", flush=True)
        el = max(1e-9, time.time() - t)
        st.update(done=done, gen_tokens=gen_tokens, tok_per_s=round(gen_tokens / el),
                  items_per_h=round(done / el * 3600))
    except Exception:
        traceback.print_exc()
        st["error"] = traceback.format_exc()[-1500:]
    print("Natija:", st, flush=True)
    json.dump(st, open(os.path.join(WORK, f"stats_{tag}.json"), "w"), indent=1)


def main():
    if JOB is not None:
        worker(json.loads(JOB))
        return


    def launch(jobs):
        procs = []
        for j in jobs:
            cache = f"/tmp/vllm_cache_{j['tag']}"
            env = dict(os.environ, OMZU_JOB=json.dumps(j), CUDA_VISIBLE_DEVICES=str(j["gpu"]),
                       VLLM_ATTENTION_BACKEND=j["backend"], VLLM_CACHE_ROOT=cache,
                       TORCHINDUCTOR_CACHE_DIR=cache + "/inductor", TRITON_CACHE_DIR=cache + "/triton")
            procs.append(subprocess.Popen([sys.executable, SCRIPT], env=env))
            time.sleep(5)
        print("Ishchilar tugadi, kodlar:", [p.wait() for p in procs], flush=True)
        res = []
        for j in jobs:
            p = os.path.join(WORK, f"stats_{j['tag']}.json")
            res.append(json.load(open(p)) if os.path.exists(p) else {"tag": j["tag"], "error": "stat yo'q"})
        for r in res:
            print("  ", {k: v for k, v in r.items() if k != "error"}, ("XATO: " + r["error"][-300:]) if "error" in r else "",
                  flush=True)
        return res


    print("Sozlama:", cfg, flush=True)
    subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"])
    t = time.time()
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", cfg.get("vllm_spec", "vllm==0.10.2"),
                        "transformers==4.56.2"], capture_output=True, text=True)
    print(f"vllm o'rnatildi ({time.time() - t:.0f}s), kod {r.returncode}", r.stderr[-800:], flush=True)

    DP = int(cfg.get("dp", 2))
    deadline = T0 + cfg.get("time_limit_hours", 11.3) * 3600
    lo = cfg.get("start", 0)

    if cfg.get("mode") == "smoke":
        n = cfg.get("per_model", 192)
        models, backends = cfg["models"], cfg["backends"]
        phase1 = launch([{"tag": f"p1_g{k}", "gpu": k, "dp": DP, "model": models[0], "backend": backends[k % len(backends)],
                          "lo": lo, "hi": lo + n, "deadline": deadline} for k in range(DP)])
        ok = [s for s in phase1 if "error" not in s and s.get("done")]
        best = max(ok, key=lambda s: s["tok_per_s"])["backend"] if ok else backends[0]
        print("Eng tez backend:", best, flush=True)
        for mi, m in enumerate(models[1:], 2):
            launch([{"tag": f"p{mi}_g{k}", "gpu": k, "dp": DP, "model": m, "backend": best,
                     "lo": lo, "hi": lo + n, "deadline": deadline} for k in range(DP)])
    else:
        hi = cfg.get("end") or 10 ** 9
        launch([{"tag": f"full_{lo}_g{k}", "gpu": k, "dp": DP, "model": cfg["models"][0], "backend": cfg["backend"],
                 "lo": lo, "hi": hi, "deadline": deadline - 600} for k in range(DP)])
    print("Tugadi.", flush=True)


if __name__ == "__main__":
    main()
