"""PyTorch research adaptation of the supplied Test-Model-Thing byte RTU model.

Derived from jrz97619761, MIT; see THIRD_PARTY_NOTICES.md. Optional and never
an execution authority. No pretrained weights were supplied. Training is explicit.
"""

from pathlib import Path
import tempfile

import torch
from torch import nn
from torch.nn import functional as F


class ByteRTU(nn.Module):
    def __init__(self, dim=32, layers=2):
        super().__init__()
        self.dim, self.depth = dim, layers
        self.embed = nn.Embedding(256, dim)
        self.decays = nn.Parameter(torch.zeros(layers, dim))
        self.norms = nn.ModuleList(nn.LayerNorm(dim) for _ in range(layers))
        self.weights = nn.ModuleList(nn.Linear(dim, dim, bias=False) for _ in range(layers))
        self.decode = nn.Linear(dim, 256)
        self.stop = nn.Linear(dim, 1)
        self.register_buffer("states", torch.zeros(layers, dim))
        self.register_buffer("embedtrace", torch.zeros(layers, 256, dim))
        self.register_buffer("decaytrace", torch.zeros(layers, dim))

    def forward(self, byte, dummy=None):
        encoded = self.embed(torch.tensor(byte, device=self.states.device))
        latent = encoded
        decay = self.decays.sigmoid()
        states = decay * self.states + encoded
        if dummy is not None:
            states = states + dummy
        for i in range(self.depth):
            latent = latent + F.silu(self.weights[i](self.norms[i](states[i])))
        return latent, states, decay, self.decode(latent), self.stop(latent).sigmoid()

    def learn(self, byte, next_byte, optimizer, end=False):
        dummy = torch.zeros_like(self.states, requires_grad=True)
        latent, states, decay, logits, stop = self(byte, dummy)
        target = self.embed(torch.tensor(next_byte, device=latent.device)).detach()
        loss = (F.relu(1-torch.sqrt(latent.var(unbiased=False)+1e-4))
                + F.mse_loss(latent, target)
                + F.cross_entropy(logits.unsqueeze(0), torch.tensor([next_byte], device=latent.device))
                + F.mse_loss(stop, torch.full_like(stop, float(end))))
        optimizer.zero_grad()
        loss.backward()
        with torch.no_grad():
            historical = self.embedtrace * decay[:, None, :]
            self.embed.weight.grad += (dummy.grad[:, None, :] * historical).sum(0)
            new_decaytrace = decay * self.decaytrace + decay * (1-decay) * self.states
            self.decays.grad.copy_(dummy.grad * new_decaytrace)
            self.embedtrace.copy_(historical)
            self.embedtrace[:, byte, :] += 1
            self.decaytrace.copy_(new_decaytrace)
            self.states.copy_(states)
        optimizer.step()
        return float(loss.detach())

    @torch.no_grad()
    def observe(self, data):
        """Update recurrent state without gradients or weight changes."""
        novelty = []
        for byte in data:
            latent, states, _, logits, _ = self(byte)
            self.states.copy_(states)
            probs = logits.softmax(-1)
            novelty.append(float(-(probs * probs.clamp_min(1e-9).log()).sum()))
        return {"bytes": len(data), "mean_predictive_entropy": sum(novelty)/max(1,len(novelty)),
                "latent_norm": float(self.states.norm()), "trained_model": False}


def train_file(source, checkpoint, steps):
    if not 1 <= steps <= 100000:
        raise ValueError("steps must be 1..100000")
    with Path(source).open("rb") as handle:
        data = handle.read(steps+1)
    if len(data)<2:
        raise ValueError("Need at least two bytes of training data")
    model = ByteRTU()
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4)
    losses = [model.learn(a, b, optimizer, i==len(data)-2) for i,(a,b) in enumerate(zip(data,data[1:]))]
    target = Path(checkpoint)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("Checkpoint already exists; choose a new output path")
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        torch.save({"format": 1, "dim": model.dim, "layers": model.depth,
                    "model": model.state_dict(), "optimizer": optimizer.state_dict()}, temporary)
        # No overwrite even if another process creates the destination while training.
        with target.open("xb") as handle:
            handle.write(temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)
    return {"steps": len(losses), "initial_loss": losses[0], "final_loss": losses[-1],
            "checkpoint": str(target), "note": "Experimental byte predictor; not a validated routing model"}


def checkpoint_hint(path, text, max_bytes=512):
    if not 1 <= max_bytes <= 4096:
        raise ValueError("TMT max_bytes must be 1..4096")
    checkpoint = Path(path)
    if checkpoint.stat().st_size > 64_000_000:
        raise ValueError("TMT checkpoint exceeds 64 MB")
    data = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if data.get("format") != 1 or not 1 <= data["dim"] <= 256 or not 1 <= data["layers"] <= 16:
        raise ValueError("Unsupported TMT checkpoint")
    model = ByteRTU(data["dim"], data["layers"])
    model.load_state_dict(data["model"], strict=True)
    summary = model.observe(text.encode()[:max_bytes])
    summary["trained_model"] = True
    return {"source": "experimental_tmt", **summary}
