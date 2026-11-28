import json

ROLE_TOKENS = {
    "system": "<|system|>",
    "user": "<|user|>",
    "assistant": "<|assistant|>",
    "tool_call": "<|assistant|><|tool_call|>",
    "tool_result": "<|tool_result|>",
    "context": "<|context|>",
}
END = "<|end|>"
TRAINABLE = {"assistant", "tool_call"}


def encode_dialog(tok, messages: list[dict], max_len: int) -> tuple[list[int], list[int]] | None:
    ids, labels = [], []
    for m in messages:
        role = m["role"]
        content = m["content"] if isinstance(m["content"], str) else json.dumps(m["content"], ensure_ascii=False)
        prefix = tok.encode(ROLE_TOKENS[role]).ids
        body = tok.encode(content + END).ids
        ids += prefix + body
        if role in TRAINABLE:
            labels += [-1] * len(prefix) + body
        else:
            labels += [-1] * (len(prefix) + len(body))
    if len(ids) > max_len:
        return None
    if all(x == -1 for x in labels):
        return None
    return ids, labels
