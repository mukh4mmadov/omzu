from pathlib import Path

from huggingface_hub import hf_hub_download

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

FILES = [
    ("wikimedia/wikipedia", "20231101.uz/train-00000-of-00001.parquet"),
    ("HuggingFaceFW/fineweb-2", "data/uzn_Latn/train/000_00000.parquet"),
    ("HuggingFaceFW/fineweb-2", "data/uzn_Cyrl/train/000_00000.parquet"),
    ("HuggingFaceFW/fineweb-edu", "sample/10BT/000_00000.parquet"),
    ("HuggingFaceFW/fineweb-edu", "sample/10BT/001_00000.parquet"),
]


def main():
    for repo, path in FILES:
        target = RAW / repo.split("/")[1]
        print(f"[yuklanmoqda] {repo}/{path}", flush=True)
        local = hf_hub_download(repo, path, repo_type="dataset", local_dir=target)
        print(f"[tayyor] {local} ({Path(local).stat().st_size / 1e6:.0f} MB)", flush=True)
    print("HAMMASI YUKLANDI")


SFT_FILES = [
    ("CohereLabs/aya_collection_language_split", "northern_uzbek/train-00000-of-00001.parquet"),
    ("CohereLabs/aya_dataset", "data/train-00000-of-00001.parquet"),
]


def download_sft():
    for repo, path in SFT_FILES:
        target = RAW / "sft" / repo.split("/")[1]
        print(f"[yuklanmoqda] {repo}/{path}", flush=True)
        local = hf_hub_download(repo, path, repo_type="dataset", local_dir=target)
        print(f"[tayyor] {local} ({Path(local).stat().st_size / 1e6:.0f} MB)", flush=True)


if __name__ == "__main__":
    import sys
    download_sft() if "sft" in sys.argv[1:] else main()
