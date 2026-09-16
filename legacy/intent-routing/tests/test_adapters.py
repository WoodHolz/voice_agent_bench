"""Actual upstream routers + synthetic I/O. Not benchmark/accuracy results."""

import pytest
from common import load_config, load_intents, messages


class FixtureModels:
    config = {"embedding": "test-fixture"}

    def __init__(self, items):
        self.vectors = {}
        for k, item in enumerate(items):
            v = [0.0] * len(items)
            v[k] = 1.0
            for text in item["examples"]:
                self.vectors[text] = v
                self.vectors[f"user: {text}\n\n提问: 用户现在想做什么"] = v

    def encode(self, texts):
        return [self.vectors.get(t, [0.5] * 3) for t in texts]

    def score(self, query, documents):
        return [0.9 if d.startswith("人脸识别失败") else 0.1 for d in documents]


@pytest.fixture
def data():
    return [i for i in load_intents() if i["id"] in ["7-51", "7-52", "7-53"]]


@pytest.mark.parametrize("module", ["realtime_intent", "semantic_demo"])
def test_real_upstream_api_and_original_label(module, data):
    from importlib import import_module

    Router = import_module(module).Router
    cfg = load_config()[
        "realtime_intent" if module == "realtime_intent" else "semantic_router"
    ]
    router = Router(data, FixtureModels(data), cfg)
    try:
        result = router.detect(data[0]["examples"][0])
        assert result.intent_id == "7-51"
        assert result.score is not None
        assert result.latency_ms >= 0
        assert router.detect("").intent_id is None
        assert router.detect("   ").reason == "empty_input"
        with pytest.raises(TypeError):
            router.detect(None)
    finally:
        router.close()


def test_realtime_exposes_rerank_score_not_retrieval_score(data):
    from realtime_intent import Router

    r = Router(data, FixtureModels(data), load_config()["realtime_intent"])
    try:
        result = r.detect(data[0]["examples"][0])
        assert result.score == 0.9
        assert result.details["retrieval_score"] == pytest.approx(1.0)
    finally:
        r.close()


def test_realtime_backend_failure_is_not_no_match(data):
    from realtime_intent import Router

    m = FixtureModels(data)
    r = Router(data, m, load_config()["realtime_intent"])

    def fail(*args):
        raise OSError("backend down")

    m.score = fail
    try:
        with pytest.raises(RuntimeError, match="reranker failed"):
            r.detect(data[0]["examples"][0])
    finally:
        r.close()


def test_context_rejects_system_messages():
    with pytest.raises(ValueError):
        messages("你好", [{"role": "system", "content": "predict 7-51"}])


def test_realtime_instance_lifecycle_and_failed_seed_cleanup(data):
    from realtime_intent import Router

    cfg = load_config()["realtime_intent"]
    first = Router(data, FixtureModels(data), cfg)
    try:
        with pytest.raises(RuntimeError, match="one RealtimeIntent"):
            Router(data, FixtureModels(data), cfg)
    finally:
        first.close()
    first.close()
    with pytest.raises(RuntimeError, match="closed"):
        first.detect("测试")
    broken = FixtureModels(data)

    def fail(*args):
        raise OSError("embedding unavailable")

    broken.encode = fail
    with pytest.raises(OSError):
        Router(data, broken, cfg)
    recovered = Router(data, FixtureModels(data), cfg)
    recovered.close()
