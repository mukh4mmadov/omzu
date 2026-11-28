import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE = str(ROOT / ".venv" / "Scripts" / "kaggle.exe")
BUILD = ROOT / "build"
TOKENS = ROOT / "data" / "tokens"


def user() -> str:
    out = subprocess.run([KAGGLE, "config", "view"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "username:" in line:
            return line.split(":", 1)[1].strip()
    sys.exit("Kaggle foydalanuvchi nomi topilmadi")


def run(*args, check=True):
    print(">", " ".join(args), flush=True)
    r = subprocess.run([KAGGLE, *args])
    if check and r.returncode:
        sys.exit(r.returncode)
    return r.returncode


def dataset_exists(ref: str) -> bool:
    r = subprocess.run([KAGGLE, "datasets", "files", ref], capture_output=True, text=True)
    return r.returncode == 0 and "404" not in (r.stdout + r.stderr)


def publish_code(u: str):
    d = BUILD / "kaggle_code"
    shutil.rmtree(d, ignore_errors=True)
    (d / "uzllm").mkdir(parents=True)
    for f in (ROOT / "uzllm").glob("*.py"):
        shutil.copy(f, d / "uzllm" / f.name)
    shutil.copytree(ROOT / "uztts", d / "uztts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "kaggle" / "run_configs.json", d / "run_configs.json")
    ref = f"{u}/uzllm-code"
    (d / "dataset-metadata.json").write_text(json.dumps(
        {"title": "uzllm-code", "id": ref, "licenses": [{"name": "CC0-1.0"}]}))
    if dataset_exists(ref):
        run("datasets", "version", "-p", str(d), "-m", "kod yangilandi", "-r", "zip")
    else:
        run("datasets", "create", "-p", str(d), "-r", "zip")


def publish_tokens(u: str, test: bool = False):
    name = "uzllm-tokens-test" if test else "uzllm-tokens"
    tok_dir = ROOT / "data" / ("tokens_test" if test else "tokens")
    tok_file = ROOT / "data" / ("tok_test.json" if test else "tokenizer.json")
    ref = f"{u}/{name}"
    shutil.copy(tok_file, tok_dir / "tokenizer.json")
    (tok_dir / "dataset-metadata.json").write_text(json.dumps(
        {"title": name, "id": ref, "licenses": [{"name": "ODC-BY-1.0"}]}))
    if dataset_exists(ref):
        run("datasets", "version", "-p", str(tok_dir), "-m", "yangilandi")
    else:
        run("datasets", "create", "-p", str(tok_dir))


def publish_sft_data(u: str):
    d = ROOT / "data" / "sft"
    ref = f"{u}/uzllm-sft"
    (d / "dataset-metadata.json").write_text(json.dumps(
        {"title": "uzllm-sft", "id": ref, "licenses": [{"name": "apache-2.0"}]}))
    if dataset_exists(ref):
        run("datasets", "version", "-p", str(d), "-m", "yangilandi")
    else:
        run("datasets", "create", "-p", str(d))


def publish_sft_kernel(u: str):
    d = BUILD / "kernel_sft"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    shutil.copy(ROOT / "kaggle" / "sft_kernel.py", d / "sft_kernel.py")
    sources = [f"{u}/uzllm-pretrain-a"] + ([f"{u}/uzllm-pretrain-b"] if kernel_exists(f"{u}/uzllm-pretrain-b") else [])
    meta = {
        "id": f"{u}/uzllm-sft-train", "title": "uzllm-sft-train", "code_file": "sft_kernel.py",
        "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
        "enable_internet": False, "competition_sources": [],
        "dataset_sources": [f"{u}/uzllm-code", f"{u}/uzllm-tokens", f"{u}/uzllm-sft"],
        "kernel_sources": sources,
    }
    (d / "kernel-metadata.json").write_text(json.dumps(meta, indent=2))
    run("kernels", "push", "-p", str(d), "--accelerator", "NvidiaTeslaT4")


def kernel_exists(ref: str) -> bool:
    r = subprocess.run([KAGGLE, "kernels", "status", ref], capture_output=True, text=True)
    return r.returncode == 0 and "404" not in (r.stdout + r.stderr) and "not found" not in (r.stdout + r.stderr).lower()


def publish_kernel(u: str, which: str):
    slug = {"smoke": "uzllm-smoke", "a": "uzllm-pretrain-a", "b": "uzllm-pretrain-b"}[which]
    cfg_name = "smoke" if which == "smoke" else "full"
    d = BUILD / f"kernel_{which}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    src = (ROOT / "kaggle" / "pretrain_kernel.py").read_text(encoding="utf-8")
    (d / "pretrain_kernel.py").write_text(f'CONFIG_NAME = "{cfg_name}"\n' + src, encoding="utf-8")

    kernel_sources = []
    if which in ("a", "b"):
        other = f"{u}/uzllm-pretrain-{'b' if which == 'a' else 'a'}"
        if kernel_exists(other):
            kernel_sources.append(other)
    meta = {
        "id": f"{u}/{slug}",
        "title": slug,
        "code_file": "pretrain_kernel.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": False,
        "dataset_sources": [f"{u}/uzllm-code", f"{u}/uzllm-tokens-test" if which == "smoke" else f"{u}/uzllm-tokens"],
        "kernel_sources": kernel_sources,
        "competition_sources": [],
    }
    (d / "kernel-metadata.json").write_text(json.dumps(meta, indent=2))
    print("Kirishlar:", meta["dataset_sources"] + kernel_sources)
    run("kernels", "push", "-p", str(d), "--accelerator", "NvidiaTeslaT4")


TEACHER_CFG = {
    "smoke": {"mode": "smoke", "models": ["Qwen/Qwen3-8B-AWQ", "Qwen/Qwen3-14B-AWQ"], "per_model": 192,
              "backends": ["XFORMERS_VLLM_V1", "TRITON_ATTN_VLLM_V1"], "quant": "awq", "dp": 2,
              "max_num_seqs": 128, "time_limit_hours": 2.5},
    "full": {"mode": "full", "models": ["Qwen/Qwen3-8B-AWQ"], "backend": "TRITON_ATTN_VLLM_V1", "quant": "awq",
             "dp": 2, "max_num_seqs": 128, "time_limit_hours": 10.8},
}


def publish_teacher_data(u: str):
    d = BUILD / "teacher_data"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    shutil.copy(ROOT / "data" / "teacher" / "prompts.jsonl", d / "prompts.jsonl")
    ref = f"{u}/omzu-teacher-prompts"
    (d / "dataset-metadata.json").write_text(json.dumps(
        {"title": "omzu-teacher-prompts", "id": ref, "licenses": [{"name": "apache-2.0"}]}))
    if dataset_exists(ref):
        run("datasets", "version", "-p", str(d), "-m", "yangilandi")
    else:
        run("datasets", "create", "-p", str(d))


def publish_teacher_kernel(u: str, mode: str, start: int = 0, end: int | None = None):
    cfg = dict(TEACHER_CFG[mode], start=start)
    if end is not None:
        cfg["end"] = end
    d = BUILD / "kernel_teacher"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    src = (ROOT / "kaggle" / "teacher_kernel.py").read_text(encoding="utf-8")
    (d / "teacher_kernel.py").write_text("CFG = " + json.dumps(cfg) + "\n" + src, encoding="utf-8")
    meta = {
        "id": f"{u}/omzu-teacher", "title": "omzu-teacher", "code_file": "teacher_kernel.py",
        "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
        "enable_internet": True, "competition_sources": [],
        "dataset_sources": [f"{u}/omzu-teacher-prompts"], "kernel_sources": [],
    }
    (d / "kernel-metadata.json").write_text(json.dumps(meta, indent=2))
    print("Sozlama:", cfg)
    run("kernels", "push", "-p", str(d), "--accelerator", "NvidiaTeslaT4")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    u = user()
    cmd = sys.argv[1]
    if cmd == "code":
        publish_code(u)
    elif cmd == "tokens":
        publish_tokens(u, test=len(sys.argv) > 2 and sys.argv[2] == "test")
    elif cmd == "kernel":
        publish_kernel(u, sys.argv[2])
    elif cmd == "sft-data":
        publish_sft_data(u)
    elif cmd == "sft":
        publish_sft_kernel(u)
    elif cmd == "teacher-data":
        publish_teacher_data(u)
    elif cmd == "teacher":
        a = sys.argv[3:]
        publish_teacher_kernel(u, sys.argv[2], int(a[0]) if a else 0, int(a[1]) if len(a) > 1 else None)
    elif cmd == "status":
        for s in ["uzllm-pretrain-a", "uzllm-pretrain-b", "uzllm-sft-train", "omzu-teacher"]:
            run("kernels", "status", f"{u}/{s}", check=False)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
