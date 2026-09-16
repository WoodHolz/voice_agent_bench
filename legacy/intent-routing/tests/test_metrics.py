from benchmark.metrics import subset, percentile


def row(expected, predicted, error=None, latency=10):
    return dict(
        id="test",
        text="测试",
        context=[],
        expected=expected,
        intent_id=predicted,
        error=error,
        score=None,
        latency_ms=latency,
    )


def test_errors_are_not_successful_ood_rejections():
    s = subset([row([], None), row([], None, "connection failed"), row([], "7-51")])
    assert s["negative_rejection_rate"] == 1 / 3
    assert s["negative_false_accept_rate"] == 1 / 3
    assert s["errors"] == 1
    assert s["latency"]["n"] == 2


def test_ambiguity_does_not_inflate_single_label_accuracy():
    s = subset(
        [row(["7-51"], "7-51"), row(["7-52"], None), row(["7-51", "7-53"], "7-53")]
    )
    assert s["accuracy"] == 0.5
    assert s["ambiguous_set_hit_rate"] == 1
    assert s["single_label_n"] == 2
    assert s["confusion_pairs"] == [
        {"expected": "7-52", "predicted": "__no_match__", "count": 1}
    ]


def test_percentiles_interpolate_and_empty_is_not_zero():
    assert percentile([], 0.5) is None
    assert percentile([0, 100], 0.5) == 50
    assert percentile([0, 100], 0.95) == 95
    assert subset([])["accuracy"] is None
