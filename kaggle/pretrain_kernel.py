import glob
import json
import os
import shutil
import subprocess
import sys

INPUT = "/kaggle/input"
WORK = "/kaggle/working"
CKPT = os.path.join(WORK, "ckpt")


def find_one(pattern):
    hits = sorted(glob.glob(os.path.join(INPUT, "**", pattern), recursive=True))
    if not hits:
        sys.exit(f"Topilmadi: {pattern}")
    return hits[0]


code_dir = os.path.dirname(os.path.dirname(find_one("uzllm/model.py")))
data_dir = os.path.dirname(find_one("meta.json"))
tokenizer = find_one("tokenizer.json")
CONFIG_NAME = globals().get("CONFIG_NAME", "full")
run_cfg = json.load(open(find_one("run_configs.json")))[CONFIG_NAME]
print("Sozlama:", CONFIG_NAME, run_cfg)
print("Kod:", code_dir, "| Ma'lumot:", data_dir)
subprocess.run(["nvidia-smi"])

os.makedirs(CKPT, exist_ok=True)
best = None
for side in glob.glob(os.path.join(INPUT, "**", "last.json"), recursive=True):
    st = json.load(open(side))["step"]
    pt = side.replace("last.json", "last.pt")
    if os.path.exists(pt) and (best is None or st > best[0]):
        best = (st, os.path.dirname(side))
if best:
    print(f"Oldingi sessiya topildi: {best[0]}-qadam -> davom ettiriladi")
    for f in os.listdir(best[1]):
        if f.endswith((".pt", ".json", ".jsonl")):
            shutil.copy(os.path.join(best[1], f), CKPT)
else:
    print("Checkpoint yo'q — noldan boshlanadi")

import torch

ngpu = torch.cuda.device_count()
cmd = ["torchrun", f"--nproc_per_node={max(1, ngpu)}", "-m", "uzllm.train",
       "--data", data_dir, "--out", CKPT, "--tokenizer", tokenizer, "--resume"]
for k, v in run_cfg.items():
    if isinstance(v, bool):
        if v:
            cmd.append(f"--{k}")
    else:
        cmd += [f"--{k}", str(v)]
print(" ".join(cmd), flush=True)
env = dict(os.environ, PYTHONPATH=code_dir, PYTHONUNBUFFERED="1",
           PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
rc = subprocess.run(cmd, env=env).returncode
print("Chiqish kodi:", rc)
