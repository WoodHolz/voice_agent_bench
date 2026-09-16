"""Stateless repeated detect(partial_text); no debounce, commits or workflow orchestration."""

import argparse
import json
import logging
from common import BASE, load_config, load_intents
from benchmark.run import make_router

SEQUENCES = [
    {
        "id": "modify",
        "expected": "7-52",
        "parts": [
            "我",
            "我刚",
            "我刚才",
            "我刚才填",
            "我刚才填错了",
            "我刚才填错了能改吗",
        ],
    },
    {
        "id": "face",
        "expected": "7-51",
        "parts": ["刷", "刷脸", "刷脸一直", "刷脸一直过不了"],
    },
    {
        "id": "refuse",
        "expected": "7-28",
        "parts": ["不用", "不用了", "不用了别", "不用了别再打了"],
    },
    {
        "id": "asr_revision",
        "expected": "7-53",
        "parts": ["链接", "链接打得开", "链接打不开", "这个链接打不开一直报错"],
    },
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--routers",
        choices=["both", "realtime_intent", "semantic_router"],
        default="both",
    )
    p.add_argument("--output", default=str(BASE / "reports/stream.json"))
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)
    from models import LocalModels

    config = load_config()
    names = (
        ["realtime_intent", "semantic_router"]
        if args.routers == "both"
        else [args.routers]
    )
    models = LocalModels(config["models"], reranker="realtime_intent" in names)
    output = {
        "config": config,
        "models": models.metadata(),
        "context_mode": "text",
        "runs": {},
    }
    for name in names:
        router = make_router(name, load_intents(), models, config, False)
        try:
            router.detect("预热，授权通知收到了")
            sequences = []
            for seq in SEQUENCES:
                rows = []
                previous = None
                for i, part in enumerate(seq["parts"]):
                    result = router.detect(part)
                    row = {
                        "partial": part,
                        **result.to_dict(),
                        "changed": i > 0 and result.intent_id != previous,
                    }
                    print(
                        json.dumps(
                            {"router": name, "sequence": seq["id"], **row},
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    rows.append(row)
                    previous = result.intent_id
                stable = next(
                    (
                        i
                        for i in range(len(rows))
                        if all(r["intent_id"] == seq["expected"] for r in rows[i:])
                    ),
                    None,
                )
                sequences.append(
                    {
                        "id": seq["id"],
                        "expected_final": seq["expected"],
                        "rows": rows,
                        "prediction_changes": sum(r["changed"] for r in rows),
                        "final_correct": rows[-1]["intent_id"] == seq["expected"],
                        "stable_correct_from_index": stable,
                        "stable_correct_from_chars": len(rows[stable]["partial"])
                        if stable is not None
                        else None,
                        "early_wrong_accepts": sum(
                            r["intent_id"] not in (None, seq["expected"])
                            for r in rows[:-1]
                        ),
                    }
                )
            output["runs"][name] = sequences
        finally:
            router.close()
    from pathlib import Path

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
