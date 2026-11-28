import math
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class GPTConfig:
    vocab_size: int = 32000
    context_len: int = 1024
    n_layer: int = 12
    n_head: int = 12
    d_model: int = 768
    mlp_hidden: int = 2048
    dropout: float = 0.0
    rope_theta: float = 10000.0


CONFIGS = {
    "tiny": GPTConfig(context_len=256, n_layer=4, n_head=4, d_model=256, mlp_hidden=704),
    "small": GPTConfig(n_layer=8, n_head=8, d_model=512, mlp_hidden=1408),
    "base": GPTConfig(),
}


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        norm = x.float().pow(2).mean(-1, keepdim=True).add(self.eps).rsqrt()
        return (x.float() * norm).type_as(x) * self.weight


def rope_cache(seq_len: int, head_dim: int, theta: float, device=None):
    inv_freq = 1.0 / (theta ** (torch.arange(0, head_dim, 2, device=device).float() / head_dim))
    t = torch.arange(seq_len, device=device).float()
    freqs = torch.outer(t, inv_freq)
    return freqs.cos(), freqs.sin()


def apply_rope(x, cos, sin):
    x1, x2 = x[..., 0::2], x[..., 1::2]
    out = torch.stack((x1 * cos - x2 * sin, x1 * sin + x2 * cos), dim=-1)
    return out.flatten(-2).type_as(x)


class Attention(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.n_head = cfg.n_head
        self.head_dim = cfg.d_model // cfg.n_head
        self.qkv = nn.Linear(cfg.d_model, 3 * cfg.d_model, bias=False)
        self.proj = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.dropout = cfg.dropout

    def forward(self, x, cos, sin, cache: dict | None = None):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q = q.view(B, T, self.n_head, self.head_dim).transpose(1, 2)
        k = k.view(B, T, self.n_head, self.head_dim).transpose(1, 2)
        v = v.view(B, T, self.n_head, self.head_dim).transpose(1, 2)
        q, k = apply_rope(q, cos, sin), apply_rope(k, cos, sin)
        past = 0
        if cache is not None:
            if "k" in cache:
                past = cache["k"].size(2)
                k = torch.cat([cache["k"], k], dim=2)
                v = torch.cat([cache["v"], v], dim=2)
            cache["k"], cache["v"] = k, v
        if past and T > 1:
            mask = torch.ones(T, past + T, dtype=torch.bool, device=x.device).tril(diagonal=past)
            y = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        else:
            y = F.scaled_dot_product_attention(
                q, k, v, is_causal=(past == 0 and T > 1), dropout_p=self.dropout if self.training else 0.0
            )
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.proj(y)


class SwiGLU(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.gate = nn.Linear(cfg.d_model, cfg.mlp_hidden, bias=False)
        self.up = nn.Linear(cfg.d_model, cfg.mlp_hidden, bias=False)
        self.down = nn.Linear(cfg.mlp_hidden, cfg.d_model, bias=False)
        self.drop = nn.Dropout(cfg.dropout)

    def forward(self, x):
        return self.drop(self.down(F.silu(self.gate(x)) * self.up(x)))


class Block(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.norm1 = RMSNorm(cfg.d_model)
        self.attn = Attention(cfg)
        self.norm2 = RMSNorm(cfg.d_model)
        self.mlp = SwiGLU(cfg)

    def forward(self, x, cos, sin, cache: dict | None = None):
        x = x + self.attn(self.norm1(x), cos, sin, cache)
        x = x + self.mlp(self.norm2(x))
        return x


class GPT(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.cfg = cfg
        self.embed = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layer))
        self.norm = RMSNorm(cfg.d_model)
        self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        self.lm_head.weight = self.embed.weight

        cos, sin = rope_cache(cfg.context_len, cfg.d_model // cfg.n_head, cfg.rope_theta)
        self.register_buffer("rope_cos", cos, persistent=False)
        self.register_buffer("rope_sin", sin, persistent=False)

        self.apply(self._init_weights)
        for name, p in self.named_parameters():
            if name.endswith("proj.weight") or name.endswith("down.weight"):
                nn.init.normal_(p, mean=0.0, std=0.02 / math.sqrt(2 * cfg.n_layer))

    @staticmethod
    def _init_weights(m):
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, mean=0.0, std=0.02)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, mean=0.0, std=0.02)

    def num_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, idx, targets=None):
        B, T = idx.shape
        assert T <= self.cfg.context_len, f"Matn juda uzun: {T} > {self.cfg.context_len}"
        x = self.embed(idx)
        cos = self.rope_cos[:T].to(x.dtype)
        sin = self.rope_sin[:T].to(x.dtype)
        for block in self.blocks:
            x = block(x, cos, sin)
        x = self.norm(x)
        if targets is None:
            return self.lm_head(x[:, [-1], :]), None
        logits = self.lm_head(x)
        loss = F.cross_entropy(logits.float().view(-1, logits.size(-1)), targets.reshape(-1), ignore_index=-1)
        return logits, loss

    def configure_optimizer(self, lr: float, weight_decay: float, betas=(0.9, 0.95), device_type="cpu"):
        decay = [p for p in self.parameters() if p.requires_grad and p.dim() >= 2]
        no_decay = [p for p in self.parameters() if p.requires_grad and p.dim() < 2]
        groups = [
            {"params": decay, "weight_decay": weight_decay},
            {"params": no_decay, "weight_decay": 0.0},
        ]
        return torch.optim.AdamW(groups, lr=lr, betas=betas, fused=(device_type == "cuda"))

    def _forward_cached(self, idx, caches: list[dict], pos: int):
        T = idx.size(1)
        x = self.embed(idx)
        cos = self.rope_cos[pos:pos + T].to(x.dtype)
        sin = self.rope_sin[pos:pos + T].to(x.dtype)
        for block, cache in zip(self.blocks, caches):
            x = block(x, cos, sin, cache)
        return self.lm_head(self.norm(x[:, -1, :]))

    @staticmethod
    def _sample(logits, history, temperature, top_k, top_p, repetition_penalty):
        logits = logits.float()
        if repetition_penalty != 1.0 and history.numel():
            prev = torch.unique(history)
            vals = logits[:, prev]
            logits[:, prev] = torch.where(vals > 0, vals / repetition_penalty, vals * repetition_penalty)
        if temperature <= 0:
            return logits.argmax(-1, keepdim=True)
        logits = logits / temperature
        if top_k:
            v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
            logits[logits < v[:, [-1]]] = -float("inf")
        probs = F.softmax(logits, dim=-1)
        if top_p:
            sp, si = torch.sort(probs, descending=True)
            sp[sp.cumsum(-1) - sp > top_p] = 0
            probs = torch.zeros_like(probs).scatter(-1, si, sp)
            probs = probs / probs.sum(-1, keepdim=True)
        return torch.multinomial(probs, 1)

    @torch.no_grad()
    def generate_stream(self, idx, max_new_tokens: int, temperature: float = 0.8, top_k: int | None = 50,
                        top_p: float | None = 0.95, repetition_penalty: float = 1.1, stop_ids: set[int] | None = None):
        idx = idx[:, -(self.cfg.context_len - max_new_tokens):] if idx.size(1) + max_new_tokens > self.cfg.context_len else idx
        caches = [{} for _ in self.blocks]
        logits = self._forward_cached(idx, caches, 0)
        pos = idx.size(1)
        recent = idx[:, -64:]
        for _ in range(max_new_tokens):
            nxt = self._sample(logits, recent, temperature, top_k, top_p, repetition_penalty)
            tid = nxt.item()
            yield tid
            if (stop_ids and tid in stop_ids) or pos >= self.cfg.context_len:
                break
            recent = torch.cat([recent, nxt], dim=1)[:, -64:]
            logits = self._forward_cached(nxt, caches, pos)
            pos += 1

    @torch.no_grad()
    def generate(self, idx, max_new_tokens: int, temperature: float = 0.8, top_k: int | None = 50,
                 top_p: float | None = 0.95, repetition_penalty: float = 1.1, stop_ids: set[int] | None = None):
        new = list(self.generate_stream(idx, max_new_tokens, temperature, top_k, top_p, repetition_penalty, stop_ids))
        return torch.cat([idx, torch.tensor([new], dtype=idx.dtype, device=idx.device)], dim=1)
