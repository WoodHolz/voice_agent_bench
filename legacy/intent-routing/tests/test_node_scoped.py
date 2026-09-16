import re
import yaml
import numpy as np
import pytest
from common import BASE, load_config, load_intents
from semantic_demo.router import Router as GlobalRouter
from node_scoped.router import Router, load_map
from node_scoped.metrics import metrics


def test_node_mapping_citations_and_gold_validity():
    mapping = load_map()
    known = {i["id"] for i in load_intents() if i["input_kind"] == "text"}
    for node, entry in mapping.items():
        assert set(entry["allowed_intents"]) <= known
        assert set(entry["allowed_intents"]) == {
            e["intent_id"] for e in entry["intent_branches"]
        }
        for edge in entry["intent_branches"]:
            for src in edge["sources"]:
                text = (
                    (BASE / "../.." / src["file"])
                    .read_text()
                    .splitlines()[src["line"] - 1]
                )
                if "quote" in src:
                    assert src["quote"] in " ".join(text.split())
                else:
                    assert re.match(rf"\| {edge['intent_id']}\s*\|", text)
    cases = yaml.safe_load((BASE / "intent_data/node_eval.yaml").read_text())["cases"]
    categories = {
        "paraphrase",
        "short_spoken",
        "polarity",
        "ambiguous",
        "insufficient",
        "ood",
        "out_of_node",
    }
    for node in mapping:
        assert categories <= {c["category"] for c in cases if c["current_node"] == node}
    for c in cases:
        allowed = mapping[c["current_node"]]["allowed_intents"]
        assert set(c["expected"]) <= set(allowed)
        if c["category"] == "out_of_node":
            assert c["global_intent"] not in allowed and c["expected"] == []
        assert (
            c["context"][0]["content"]
            == mapping[c["current_node"]]["previous_assistant"]
        )


class SyntheticModels:
    config = {"embedding": "synthetic-test-only"}

    def __init__(self, items):
        self.calls = []
        vectors = {
            "7-52": [1.0, 0.0],
            "7-40": [0.9, float(np.sqrt(0.19))],
            "7-41": [-1.0, 0.0],
        }
        self.vectors = {text: vectors[i["id"]] for i in items for text in i["examples"]}

    def encode(self, texts):
        self.calls.append(texts)
        return [self.vectors.get(t, [1.0, 0.0]) for t in texts]


def test_filter_happens_before_similarity_and_topk(monkeypatch):
    items = [i for i in load_intents() if i["id"] in ["7-40", "7-41", "7-52"]]
    model = SyntheticModels(items)
    cfg = {**load_config()["semantic_router"], "top_k": 1}
    global_router = GlobalRouter(items, model, cfg)
    scoped = Router(
        items, model, cfg, {"b16-2-a": {"allowed_intents": ["7-40", "7-41"]}}
    )
    assert global_router.detect("synthetic query").intent_id == "7-52"
    import semantic_router.index.local as local

    original = local.similarity_matrix
    counts = []

    def observe(vector, index):
        counts.append(len(index))
        return original(vector, index)

    monkeypatch.setattr(local, "similarity_matrix", observe)
    result = scoped.detect("synthetic query", current_node="b16-2-a")
    assert result.intent_id == "7-40"  # global-then-discard would have returned None
    assert counts == [sum(len(i["examples"]) for i in items if i["id"] != "7-52")]
    assert model.calls[-1] == [
        "synthetic query"
    ]  # neither node ID nor assistant text encoded
    with pytest.raises(ValueError, match="Unknown"):
        scoped.detect("", current_node="not-a-node")
    assert scoped.detect("", current_node="b16-2-a").intent_id is None
    with pytest.raises(TypeError):
        scoped.detect("x", current_node="b16-2-a", context=[])


def row(expected, predicted, category="polarity", error=None):
    return dict(
        id="1",
        text="测试",
        current_node="n",
        expected=expected,
        intent_id=predicted,
        score=None,
        error=error,
        allowed_intents=["7-40", "7-41"],
        category=category,
        latency_ms=10,
    )


def test_invalid_vs_forced_match_and_rejection_precision():
    rows = [
        row(["7-40"], "7-40"),
        row([], None, "ood"),
        row([], "7-40", "out_of_node"),
        row([], "7-52", "out_of_node"),
        row(["7-41"], None),
    ]
    m = metrics(rows)
    assert m["accuracy"] == 0.5
    assert m["invalid_intent_rate"] == 0.2
    assert m["out_of_node_forced_match_rate"] == 0.5
    assert m["rejection_precision"] == 0.5
    assert m["rejection_recall"] == pytest.approx(1 / 3)
    assert m["overall_accuracy_including_rejection"] == 0.4


def test_backend_error_is_not_rejection():
    m = metrics([row([], None, "ood", "backend error")])
    assert m["rejection_recall"] == 0
    assert m["rejection_precision"] is None
    assert m["errors"] == 1
    assert m["latency"]["n"] == 0
