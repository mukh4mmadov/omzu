from pathlib import Path

from tokenizers import Tokenizer, decoders, models, normalizers, pre_tokenizers, trainers

EOT = "<|endoftext|>"
SPECIAL_TOKENS = [
    EOT,
    "<|pad|>",
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<|end|>",
    "<|tool_call|>",
    "<|tool_result|>",
    "<|context|>",
] + [f"<|reserved_{i}|>" for i in range(7)]


def train_tokenizer(texts, vocab_size: int = 32000) -> Tokenizer:
    tok = Tokenizer(models.BPE(byte_fallback=False))
    tok.normalizer = normalizers.NFC()
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=True)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=5,
        special_tokens=SPECIAL_TOKENS,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=True,
    )
    tok.train_from_iterator(texts, trainer=trainer)
    return tok


def load_tokenizer(path: str | Path) -> Tokenizer:
    return Tokenizer.from_file(str(path))
