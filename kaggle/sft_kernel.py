import glob
import json
import os
import subprocess
import sys

INPUT = "/kaggle/input"


def find_one(pattern):
    hits = sorted(glob.glob(os.path.join(INPUT, "**", pattern), recursive=True))
    if not hits:
        sys.exit(f"Topilmadi: {pattern}")
    return hits[0]


code_dir = os.path.dirname(os.path.dirname(find_one("uzllm/model.py")))
tokenizer = find_one("tokenizer.json")
sft_dir = os.path.dirname(find_one("train.jsonl"))

best = None
for side in glob.glob(os.path.join(INPUT, "**", "last.json"), recursive=True):
    st = json.load(open(side))["step"]
    pt = os.path.join(os.path.dirname(side), "best.pt")
    if os.path.exists(pt) and (best is None or st > best[0]):
        best = (st, pt)
if not best:
    sys.exit("Pretraining checkpoint (best.pt) topilmadi")
print(f"Asos: {best[1]} (pretraining {best[0]}-qadam)")
subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"])

import torch

ngpu = max(1, torch.cuda.device_count())
cmd = ["torchrun", f"--nproc_per_node={ngpu}", "-m", "uzllm.sft", "--init", best[1], "--data", sft_dir,
       "--tokenizer", tokenizer, "--out", "/kaggle/working/chat", "--epochs", "2", "--batch-tokens", "12288",
       "--grad-accum", "4", "--lr", "1e-4"]
print(" ".join(cmd), flush=True)
env = dict(os.environ, PYTHONPATH=code_dir, PYTHONUNBUFFERED="1", PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
print("Chiqish kodi:", subprocess.run(cmd, env=env).returncode)
