"""Node-relative metrics; errors are never counted as successful rejections."""

from collections import Counter
from benchmark.metrics import percentile


def ratio(n, d):
    return n / d if d else None


def metrics(rows):
    positive = [r for r in rows if len(r["expected"]) == 1]
    negative = [r for r in rows if not r["expected"]]
    ambiguous = [r for r in rows if len(r["expected"]) > 1]
    ok = lambda r: r.get("error") is None
    correct = lambda r: ok(r) and (
        r["intent_id"] in r["expected"] if r["expected"] else r["intent_id"] is None
    )
    reject = lambda r: ok(r) and r["intent_id"] is None
    invalid = (
        lambda r: ok(r)
        and r["intent_id"] is not None
        and r["intent_id"] not in r["allowed_intents"]
    )
    strict = positive + negative
    true_rejects = sum(reject(r) for r in negative)
    # Ambiguous acceptable sets are not negative truth; exclude them from reject precision.
    predicted_rejects = sum(reject(r) for r in strict)
    latency_values = [r["latency_ms"] for r in rows if ok(r) and r["text"].strip()]
    matrix = Counter(
        (
            r["expected"][0] if r["expected"] else "__reject__",
            "__error__" if not ok(r) else (r["intent_id"] or "__reject__"),
        )
        for r in strict
    )
    out = [r for r in rows if r["category"] == "out_of_node"]
    return {
        "n": len(rows),
        "independent_cases": len({r["id"] for r in rows}),
        "positive_n": len(positive),
        "negative_n": len(negative),
        "ambiguous_n": len(ambiguous),
        "accuracy": ratio(sum(map(correct, positive)), len(positive)),
        "overall_accuracy_including_rejection": ratio(
            sum(map(correct, strict)), len(strict)
        ),
        "ambiguous_set_hit_rate": ratio(sum(map(correct, ambiguous)), len(ambiguous)),
        "ambiguous_rejection_rate": ratio(sum(map(reject, ambiguous)), len(ambiguous)),
        "invalid_intent_rate": ratio(sum(map(invalid, rows)), len(rows)),
        "invalid_among_accepted": ratio(
            sum(map(invalid, rows)),
            sum(ok(r) and r["intent_id"] is not None for r in rows),
        ),
        "rejection_precision": ratio(true_rejects, predicted_rejects),
        "rejection_recall": ratio(true_rejects, len(negative)),
        "false_rejection_rate": ratio(sum(map(reject, positive)), len(positive)),
        "ood_rejection_rate": ratio(
            sum(reject(r) for r in rows if r["category"] == "ood"),
            sum(r["category"] == "ood" for r in rows),
        ),
        "out_of_node_rejection_rate": ratio(sum(map(reject, out)), len(out)),
        "forced_in_scope_match_rate": ratio(
            sum(ok(r) and r["intent_id"] in r["allowed_intents"] for r in negative),
            len(negative),
        ),
        "out_of_node_forced_match_rate": ratio(
            sum(ok(r) and r["intent_id"] in r["allowed_intents"] for r in out), len(out)
        ),
        "errors": sum(not ok(r) for r in rows),
        "latency": {
            "n": len(latency_values),
            **{
                f"p{int(q * 100)}_ms": percentile(latency_values, q)
                for q in [0.5, 0.95, 0.99]
            },
        },
        "confusion_matrix": [
            {"expected": a, "predicted": b, "count": n}
            for (a, b), n in sorted(matrix.items())
        ],
        "confusion_pairs": [
            {"expected": a, "predicted": b, "count": n}
            for (a, b), n in matrix.most_common()
            if a != b
        ],
        "confusion_cases": [
            {
                "id": r["id"],
                "node": r["current_node"],
                "text": r["text"],
                "expected": r["expected"],
                "predicted": r["intent_id"],
                "score": r["score"],
                "error": r.get("error"),
            }
            for r in rows
            if not correct(r)
        ],
    }


def summarize(rows):
    primary = [r for r in rows if r["split"] != "source_overlap"]
    keys = lambda f: sorted({f(r) for r in primary}, key=str)
    return {
        "primary": metrics(primary),
        "source_overlap": metrics([r for r in rows if r["split"] == "source_overlap"]),
        "all_requests": metrics(rows),
        "per_node": {
            node: metrics([r for r in primary if r["current_node"] == node])
            for node in keys(lambda r: r["current_node"])
        },
        "per_intent": {
            i: metrics([r for r in primary if r["expected"] == [i]])
            for i in keys(lambda r: r["expected"][0] if len(r["expected"]) == 1 else "")
            if i
        },
        "per_category": {
            c: metrics([r for r in primary if r["category"] == c])
            for c in keys(lambda r: r["category"])
        },
        "by_candidate_count": {
            str(k): metrics([r for r in primary if r["candidate_count"] == k])
            for k in keys(lambda r: r["candidate_count"])
        },
    }
