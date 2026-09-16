"""Metrics keep backend errors, ambiguous golds and resubstitution separate."""

from collections import Counter
import math


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def latency(rows):
    values = [
        r["latency_ms"] for r in rows if r.get("error") is None and r["text"].strip()
    ]
    return {
        "n": len(values),
        **{f"p{int(q * 100)}_ms": percentile(values, q) for q in (0.5, 0.95, 0.99)},
    }


def subset(rows):
    exact = [r for r in rows if len(r["expected"]) == 1]
    negatives = [r for r in rows if not r["expected"]]
    ambiguous = [r for r in rows if len(r["expected"]) > 1]
    successes = [r for r in rows if r.get("error") is None]
    matched = [r for r in successes if r["intent_id"] is not None]
    correct = lambda r: r.get("error") is None and r["intent_id"] in r["expected"]
    rejected = [r for r in successes if r["intent_id"] is None]
    ratio = lambda n, d: n / d if d else None
    per_intent = {}
    for ident in sorted(
        {r["expected"][0] for r in exact}, key=lambda s: int(s.split("-")[1])
    ):
        rr = [r for r in exact if r["expected"] == [ident]]
        per_intent[ident] = {
            "n": len(rr),
            "correct": sum(map(correct, rr)),
            "accuracy": ratio(sum(map(correct, rr)), len(rr)),
            "rejected": sum(
                r.get("error") is None and r["intent_id"] is None for r in rr
            ),
            "errors": sum(r.get("error") is not None for r in rr),
        }
    pairs = Counter(
        (r["expected"][0], r["intent_id"] or "__no_match__")
        for r in exact
        if r.get("error") is None and not correct(r)
    )
    neg_ok = sum(r.get("error") is None and r["intent_id"] is None for r in negatives)
    return {
        "n": len(rows),
        "single_label_n": len(exact),
        "accuracy": ratio(sum(map(correct, exact)), len(exact)),
        "macro_intent_accuracy": ratio(
            sum(v["accuracy"] for v in per_intent.values()), len(per_intent)
        ),
        "no_match_rate": ratio(len(rejected), len(successes)),
        "coverage": ratio(len(matched), len(rows)),
        "negative_n": len(negatives),
        "negative_rejection_rate": ratio(neg_ok, len(negatives)),
        "negative_false_accept_rate": ratio(
            sum(
                r.get("error") is None and r["intent_id"] is not None for r in negatives
            ),
            len(negatives),
        ),
        "in_domain_false_rejection_rate": ratio(
            sum(r.get("error") is None and r["intent_id"] is None for r in exact),
            len(exact),
        ),
        "ambiguous_n": len(ambiguous),
        "ambiguous_set_hit_rate": ratio(sum(map(correct, ambiguous)), len(ambiguous)),
        "ambiguous_rejection_rate": ratio(
            sum(r.get("error") is None and r["intent_id"] is None for r in ambiguous),
            len(ambiguous),
        ),
        "errors": len(rows) - len(successes),
        "latency": latency(rows),
        "per_intent": per_intent,
        "confusion_pairs": [
            {"expected": a, "predicted": b, "count": n}
            for (a, b), n in pairs.most_common()
        ],
        "confusion_cases": [
            {
                "id": r["id"],
                "text": r["text"],
                "context": r["context"],
                "expected": r["expected"],
                "predicted": r["intent_id"],
                "score": r["score"],
                "error": r.get("error"),
            }
            for r in rows
            if r.get("error")
            or (r["expected"] and not correct(r))
            or (not r["expected"] and r["intent_id"] is not None)
        ],
    }


def summarize(rows):
    return {
        "heldout": subset([r for r in rows if r["split"] == "heldout"]),
        "by_split": {
            key: subset([r for r in rows if r["split"] == key])
            for key in sorted({r["split"] for r in rows})
        },
        "by_category": {
            key: subset([r for r in rows if r["category"] == key])
            for key in sorted({r["category"] for r in rows})
        },
        "all_requests": subset(rows),
    }
