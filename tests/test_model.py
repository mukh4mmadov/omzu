import torch

from uzllm.model import CONFIGS, GPT, GPTConfig


def test_forward_and_loss():
    cfg = GPTConfig(vocab_size=100, context_len=32, n_layer=2, n_head=2, d_model=32, mlp_hidden=64)
    m = GPT(cfg)
    x = torch.randint(0, 100, (2, 16))
    logits, loss = m(x, x)
    assert logits.shape == (2, 16, 100)
    assert 3.5 < loss.item() < 5.5


def test_can_overfit_tiny_batch():
    torch.manual_seed(0)
    cfg = GPTConfig(vocab_size=50, context_len=16, n_layer=2, n_head=2, d_model=32, mlp_hidden=64)
    m = GPT(cfg)
    opt = m.configure_optimizer(lr=3e-3, weight_decay=0.0)
    x = torch.randint(0, 50, (4, 16))
    for _ in range(150):
        _, loss = m(x[:, :-1], x[:, 1:])
        opt.zero_grad()
        loss.backward()
        opt.step()
    assert loss.item() < 0.5


def test_generate_and_sizes():
    m = GPT(GPTConfig(vocab_size=100, context_len=32, n_layer=1, n_head=2, d_model=32, mlp_hidden=64)).eval()
    out = m.generate(torch.zeros(1, 1, dtype=torch.long), max_new_tokens=5)
    assert out.shape == (1, 6)
    n = GPT(CONFIGS["base"]).num_params()
    assert 100e6 < n < 125e6, n


def test_kv_cache_matches_full_forward():
    torch.manual_seed(0)
    m = GPT(GPTConfig(vocab_size=100, context_len=64, n_layer=2, n_head=2, d_model=32, mlp_hidden=64)).eval()
    x = torch.randint(0, 100, (1, 20))
    with torch.no_grad():
        full = m(x)[0][:, -1, :]
        caches = [{} for _ in m.blocks]
        m._forward_cached(x[:, :12], caches, 0)
        for t in range(12, 20):
            inc = m._forward_cached(x[:, t:t + 1], caches, t)
    assert torch.allclose(full, inc, atol=1e-4)
    with torch.no_grad():
        caches = [{} for _ in m.blocks]
        m._forward_cached(x[:, :10], caches, 0)
        multi = m._forward_cached(x[:, 10:20], caches, 10)
    assert torch.allclose(full, multi, atol=1e-4)
