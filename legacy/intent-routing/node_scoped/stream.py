"""Stateless A vs C partial ASR experiment; no tracker, voting or commits."""

import argparse
import json
import logging
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
from common import BASE, load_config, load_intents, sha256
from models import LocalModels
from semantic_demo.router import Router as GlobalRouter
from node_scoped.router import Router as ScopedRouter, load_map
from benchmark.stream import SEQUENCES


def sequences():
    assignments = {
        "modify": ("a4", [0, 1, 2, 3]),
        "face": ("a4", [0, 1, 2]),
        "refuse": ("5-4-c", [0]),
        "asr_revision": ("a4", [0]),
    }
    result = [
        {
            **s,
            "current_node": assignments[s["id"]][0],
            "insufficient_indices": assignments[s["id"]][1],
            "source": "previous benchmark.stream.SEQUENCES",
        }
        for s in SEQUENCES
    ]
    extra = [
        ("not_received", "4-2", "7-38", ["没", "没收到", "没收到授权通知"], [0]),
        (
            "not_found",
            "b12-4",
            "7-41",
            ["找", "找了", "找了一圈", "找了一圈没找到"],
            [0, 1, 2],
        ),
        (
            "verify",
            "a1-5",
            "7-16",
            ["我", "我先", "我先问HR", "我先问HR确认来电真假"],
            [0, 1],
        ),
        (
            "all_done",
            "5-2-b-2",
            "7-46",
            ["签名", "签名和人脸", "签名和人脸都做了", "签名人脸提交都做完了"],
            [0, 1],
        ),
        (
            "not_submitted",
            "5-2-b-2",
            "7-47",
            ["提交", "提交好像", "提交好像没点"],
            [0, 1],
        ),
    ]
    result += [
        {
            "id": i,
            "current_node": n,
            "expected": e,
            "parts": p,
            "insufficient_indices": ins,
            "source": "针对产品4-2/b12-4/a1-5/5-2-b-2极性分支构造",
        }
        for i, n, e, p, ins in extra
    ]
    return result


def run(output, repeat=3):
    if repeat < 1:
        raise ValueError("repeat must be positive")
    logging.basicConfig(level=logging.ERROR)
    cfg = load_config()
    mapping = load_map()
    models = LocalModels(cfg["models"], reranker=False)
    routers = {
        "A_global_text": GlobalRouter(load_intents(), models, cfg["semantic_router"]),
        "C_node_text": ScopedRouter(
            load_intents(), models, cfg["semantic_router"], mapping
        ),
    }
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "models": models.metadata(),
        "map_sha256": sha256(BASE / "intent_data/workflow_intent_map.yaml"),
        "repeat": repeat,
        "notes": "insufficient标签为人工实验标注；early_wrong_vs_final不等于每个修订假设的语义错误。没有预测状态、提交或动作。",
        "runs": {name: [] for name in routers},
    }
    try:
        for name, router in routers.items():
            for _ in range(2):
                if name.startswith("C_"):
                    router.detect("人脸识别一直失败", current_node="a4")
                else:
                    router.detect("人脸识别一直失败")
        for rep in range(repeat):
            for seq in sequences():
                results = {name: [] for name in routers}
                for idx, text in enumerate(seq["parts"]):
                    order = list(routers)
                    if (rep + idx) % 2:
                        order.reverse()
                    for name in order:
                        start = perf_counter()
                        try:
                            result = (
                                routers[name].detect(
                                    text, current_node=seq["current_node"]
                                )
                                if name.startswith("C_")
                                else routers[name].detect(text)
                            )
                            row = result.to_dict()
                            row["error"] = None
                        except Exception as exc:
                            row = {
                                "intent_id": None,
                                "score": None,
                                "latency_ms": (perf_counter() - start) * 1000,
                                "error": str(exc),
                            }
                        row.update(
                            partial=text,
                            index=idx,
                            insufficient=idx in seq["insufficient_indices"],
                            rejected=row["intent_id"] is None and row["error"] is None,
                            changed=bool(results[name])
                            and results[name][-1]["intent_id"] != row["intent_id"],
                        )
                        results[name].append(row)
                for name, rows in results.items():
                    stable = next(
                        (
                            i
                            for i in range(len(rows))
                            if all(
                                r["error"] is None and r["intent_id"] == seq["expected"]
                                for r in rows[i:]
                            )
                        ),
                        None,
                    )
                    report["runs"][name].append(
                        {
                            **seq,
                            "repeat": rep,
                            "candidate_count": len(
                                mapping[seq["current_node"]]["allowed_intents"]
                            ),
                            "rows": rows,
                            "prediction_changes": sum(r["changed"] for r in rows),
                            "final_correct": rows[-1]["error"] is None
                            and rows[-1]["intent_id"] == seq["expected"],
                            "stable_correct_from_index": stable,
                            "stable_correct_from_chars": len(rows[stable]["partial"])
                            if stable is not None
                            else None,
                            "early_wrong_vs_final": sum(
                                r["error"] is None
                                and r["intent_id"] not in (None, seq["expected"])
                                for r in rows[:-1]
                            ),
                            "insufficient_accepts": sum(
                                r["insufficient"]
                                and r["error"] is None
                                and r["intent_id"] is not None
                                for r in rows
                            ),
                            "insufficient_max_score": max(
                                (
                                    r["score"]
                                    for r in rows
                                    if r["insufficient"] and r["score"] is not None
                                ),
                                default=None,
                            ),
                        }
                    )
    finally:
        for router in routers.values():
            router.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(output)
    if any(
        r["error"] for seqs in report["runs"].values() for s in seqs for r in s["rows"]
    ):
        raise RuntimeError("ASR benchmark errors recorded")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument(
        "--output", type=Path, default=BASE / "reports/node_scoped/stream.json"
    )
    a = p.parse_args()
    run(a.output, a.repeat)
