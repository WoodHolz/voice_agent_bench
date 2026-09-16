"""Shared data and result contract; no workflow transitions."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
import hashlib
import yaml

BASE = Path(__file__).resolve().parent


@dataclass
class Detection:
    intent_id: str | None
    score: float | None
    latency_ms: float
    score_kind: str
    reason: str | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def load_intents(path=None):
    return yaml.safe_load(Path(path or BASE / "intent_data/intents.yaml").read_text())[
        "intents"
    ]


def load_config(path=None):
    return yaml.safe_load(Path(path or BASE / "config.yaml").read_text())


def messages(text, context=None):
    """Context is previous messages only; no expected labels, branches or state masks."""
    history = context or []
    if not isinstance(history, list):
        raise TypeError("context must be a list of prior role/content messages")
    result = []
    for msg in history:
        if msg.get("role") not in ("user", "assistant") or not isinstance(
            msg.get("content"), str
        ):
            raise ValueError("context requires user/assistant role and string content")
        result.append({"role": msg["role"], "content": msg["content"]})
    return result + [{"role": "user", "content": text}]


def render(text, context=None):
    if not context:
        return text
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages(text, context))


def examples(intents, with_context=False):
    return [
        (item["id"], render(text, item["example_context"] if with_context else None))
        for item in intents
        if item["input_kind"] == "text"
        for text in item["examples"]
    ]


def empty_result(start):
    # No timer/VAD state: blank text cannot establish product intent 7-1.
    return Detection(
        None, None, (perf_counter() - start) * 1000, "not_scored", "empty_input"
    )


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
