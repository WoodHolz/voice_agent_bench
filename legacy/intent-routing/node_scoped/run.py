"""Matched A/B/C, round-robin interleaving. Does not touch earlier reports."""

import argparse
import json
import logging
import random
import platform
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import yaml
from common import BASE, load_config, load_intents, sha256
from benchmark.run import versions, revision
from models import LocalModels
from semantic_demo.router import Router as GlobalRouter
from node_scoped.router import Router as ScopedRouter, load_map
from node_scoped.metrics import summarize


def run(output, repeat=3):
    if repeat < 1:
        raise ValueError("repeat must be positive")
    logging.basicConfig(level=logging.ERROR)
    cfg = load_config()
    intents = load_intents()
    mapping = load_map()
    dataset = BASE / "intent_data/node_eval.yaml"
    cases = yaml.safe_load(dataset.read_text())["cases"]
    original_hashes = {
        str(p.relative_to(BASE)): sha256(p)
        for p in (BASE / "reports").glob("*")
        if p.is_file()
    }
    start = perf_counter()
    models = LocalModels(cfg["models"], reranker=False)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "model_load_ms": (perf_counter() - start) * 1000,
        "models": models.metadata(),
        "packages": versions(),
        "platform": platform.platform(),
        "cpu": next(
            (
                l.split(":", 1)[1].strip()
                for l in Path("/proc/cpuinfo").read_text().splitlines()
                if l.startswith("model name")
            ),
            platform.processor(),
        ),
        "source_revisions": {
            "semantic_router": revision(BASE / "../../semantic-router")
        },
        "hashes": {
            "intents": sha256(BASE / "intent_data/intents.yaml"),
            "node_map": sha256(BASE / "intent_data/workflow_intent_map.yaml"),
            "eval": sha256(dataset),
        },
        "source_hashes": {
            str(p.relative_to(BASE)): sha256(p)
            for p in (BASE / "node_scoped").glob("*.py")
        },
        "repeat": repeat,
        "seed": 42,
        "concurrency": 1,
        "independent_cases": len(cases),
        "unique_user_texts": len({c["text"] for c in cases}),
        "query_cache": False,
        "protocol": "A/B/C rotated per case and seeded shuffled. B index uses previous baseline intent-level prompts; test context is fixed per node.",
        "runs": {},
        "previous_artifacts_hashes": original_hashes,
    }
    factories = {
        "A_global_text": lambda: GlobalRouter(intents, models, cfg["semantic_router"]),
        "B_global_context": lambda: GlobalRouter(
            intents, models, cfg["semantic_router"], with_context=True
        ),
        "C_node_text": lambda: ScopedRouter(
            intents, models, cfg["semantic_router"], mapping
        ),
        "S_node_plus_sides": lambda: ScopedRouter(
            intents, models, cfg["semantic_router"], mapping, include_sides=True
        ),
    }
    routers = {}
    try:
        for name, factory in factories.items():
            start = perf_counter()
            routers[name] = factory()
            report["runs"][name] = {
                "index_init_ms": (perf_counter() - start) * 1000,
                "rows": [],
            }
        warm = intents[50]["examples"][0]
        for name, router in routers.items():
            start = perf_counter()
            for _ in range(3):
                if name.startswith(("C_", "S_")):
                    router.detect(warm, current_node="a4")
                else:
                    router.detect(warm)
            report["runs"][name]["warmup_three_ms"] = (perf_counter() - start) * 1000
        order = [(rep, c) for rep in range(repeat) for c in cases]
        random.Random(42).shuffle(order)
        names = list(routers)
        for pos, (rep, case) in enumerate(order):
            node = mapping[case["current_node"]]
            for name in names[pos % len(names) :] + names[: pos % len(names)]:
                # S only audits documented main flow, leaving side-subtree decisions untouched.
                if name.startswith("S_") and not node["main_flow"]:
                    continue
                allowed = node["allowed_intents"]
                expected = case["expected"]
                category = case["category"]
                if name.startswith("S_"):
                    allowed = node["allowed_including_documented_sides"]
                    if case.get("documented_side_route"):
                        expected = [case["global_intent"]]
                        category = "legal_side_route"
                row = {
                    **case,
                    "repeat": rep,
                    "allowed_intents": allowed,
                    "candidate_count": len(allowed),
                    "expected": expected,
                    "category": category,
                    "actual_search_count": 58
                    if name.startswith(("A_", "B_"))
                    else len(allowed),
                }
                start = perf_counter()
                try:
                    router = routers[name]
                    if name.startswith(("C_", "S_")):
                        result = router.detect(
                            case["text"], current_node=case["current_node"]
                        )
                    elif name.startswith("B_"):
                        result = router.detect(case["text"], context=case["context"])
                    else:
                        result = router.detect(case["text"])
                    row.update(result.to_dict())
                    row["error"] = None
                except Exception as exc:
                    row.update(
                        intent_id=None,
                        score=None,
                        latency_ms=(perf_counter() - start) * 1000,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                report["runs"][name]["rows"].append(row)
            if pos % 50 == 0:
                print(
                    f"node benchmark {pos + 1}/{len(order)} cases × configs", flush=True
                )
        for run_data in report["runs"].values():
            run_data["summary"] = summarize(run_data["rows"])
        # Apples-to-apples side audit: re-score A/B under the SAME expanded valid set/gold.
        for name in ["A_global_text", "B_global_context"]:
            rows = []
            for row in report["runs"][name]["rows"]:
                node = mapping[row["current_node"]]
                if not node["main_flow"]:
                    continue
                row = {
                    **row,
                    "allowed_intents": node["allowed_including_documented_sides"],
                    "candidate_count": len(node["allowed_including_documented_sides"]),
                }
                if row.get("documented_side_route"):
                    row.update(
                        expected=[row["global_intent"]], category="legal_side_route"
                    )
                rows.append(row)
            report["runs"][name]["side_audit_summary"] = summarize(rows)
        # Paired per-case changes, using first repetition (extra reps are timing samples).
        indexed = {
            name: {r["id"]: r for r in run_data["rows"] if r["repeat"] == 0}
            for name, run_data in report["runs"].items()
        }
        changes = []
        for case_id, a in indexed["A_global_text"].items():
            c = indexed["C_node_text"][case_id]
            if a["intent_id"] != c["intent_id"]:
                changes.append(
                    {
                        "id": case_id,
                        "node": a["current_node"],
                        "text": a["text"],
                        "expected": a["expected"],
                        "A": a["intent_id"],
                        "C": c["intent_id"],
                        "category": a["category"],
                        "split": a["split"],
                    }
                )
        report["paired_changes_A_C"] = changes
        report["all_previous_artifacts_unchanged"] = all(
            sha256(BASE / p) == h for p, h in original_hashes.items()
        )
    finally:
        for router in routers.values():
            router.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(output, flush=True)
    if any(r["summary"]["all_requests"]["errors"] for r in report["runs"].values()):
        raise RuntimeError("Backend errors recorded")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument(
        "--output", type=Path, default=BASE / "reports/node_scoped/benchmark.json"
    )
    args = p.parse_args()
    run(args.output, args.repeat)
