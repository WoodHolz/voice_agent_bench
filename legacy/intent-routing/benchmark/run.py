"""Run from the PoC directory: python -m benchmark.run --routers both --modes both."""

import argparse
import importlib.metadata
import json
import logging
import platform
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import yaml
from common import BASE, load_config, load_intents, sha256
from benchmark.metrics import summarize


def make_router(name, intents, models, config, with_context):
    if name == "realtime_intent":
        from realtime_intent import Router

        return Router(intents, models, config[name], with_context)
    from semantic_demo import Router

    return Router(intents, models, config["semantic_router"], with_context)


def versions():
    names = [
        "semantic-router",
        "sentence-transformers",
        "torch",
        "transformers",
        "qdrant-client",
        "numpy",
        "pydantic",
        "pyyaml",
    ]
    result = {n: importlib.metadata.version(n) for n in names}
    dist = importlib.metadata.distribution("semantic-router")
    result["semantic-router-source"] = json.loads(
        dist.read_text("direct_url.json") or "{}"
    )
    return result


def revision(path):
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Intent routing benchmark",
        "",
        "主准确率仅计 heldout 单标签样本；歧义集合命中率、原话重叠、OOD、错误另列。",
        "延迟为进程内串行 detect 墙钟耗时，包含模型推理与检索，不含 ASR/TTS、HTTP、队列或模型加载。",
        "CPU 多语言小模型配置，不代表上游 Qwen GPU 默认性能；阈值尚未校准。",
        "",
        "| Router / mode | Heldout accuracy | Macro | Reject (ID) | OOD reject | p50 ms | p95 ms | p99 ms | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    fmt = lambda x: "N/A" if x is None else f"{x:.3f}"
    for name, run in report["runs"].items():
        if "summary" not in run:
            lines.extend(["", f"{name}: 初始化失败：{run.get('error')}"])
            continue
        s = run["summary"]
        h = s["heldout"]
        a = s["all_requests"]
        ood = s["by_category"].get("ood", {})
        l = a["latency"]
        cells = [
            name,
            fmt(h["accuracy"]),
            fmt(h["macro_intent_accuracy"]),
            fmt(h["in_domain_false_rejection_rate"]),
            fmt(ood.get("negative_rejection_rate")),
            fmt(l["p50_ms"]),
            fmt(l["p95_ms"]),
            fmt(l["p99_ms"]),
            str(a["errors"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    for name, run in report["runs"].items():
        if "summary" not in run:
            continue
        s = run["summary"]
        lines += [
            "",
            f"## {name}",
            "",
            f"索引初始化：{run['index_init_ms']:.1f} ms；首个 detect：{run['first_detect_ms']:.1f} ms。",
            "",
            "最常见留出集混淆：",
        ]
        for c in s["heldout"]["confusion_pairs"][:10]:
            lines.append(f"- {c['expected']} → {c['predicted']}: {c['count']}")
        lines += [
            "",
            "逐意图准确率：",
            "",
            "| Intent | Correct / n | Accuracy |",
            "|---|---:|---:|",
        ]
        for ident, v in s["heldout"]["per_intent"].items():
            lines.append(
                f"| {ident} | {v['correct']}/{v['n']} | {fmt(v['accuracy'])} |"
            )
        lines += [
            "",
            "分类别结果（context_pair 在 text 模式下缺少判定上下文，仅作诊断）：",
            "",
            "| Category | n | Accuracy | Negative rejection | Ambiguous set hit |",
            "|---|---:|---:|---:|---:|",
        ]
        for cat, v in s["by_category"].items():
            lines.append(
                f"| {cat} | {v['n']} | {fmt(v['accuracy'])} | {fmt(v['negative_rejection_rate'])} | {fmt(v['ambiguous_set_hit_rate'])} |"
            )
    lines += [
        "",
        "完整配置、包/模型版本、逐条结果、分数语义和混淆文本见同名 JSON。",
        "重复请求不增加独立样本数；这批人工小样本不足以代表线上分布。p99 是样本分位数，不是生产 SLA。",
    ]
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--routers",
        choices=["both", "realtime_intent", "semantic_router"],
        default="both",
    )
    parser.add_argument("--modes", choices=["both", "text", "context"], default="both")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--eval", type=Path, default=BASE / "intent_data/eval.yaml")
    parser.add_argument("--output", type=Path, default=BASE / "reports/baseline.json")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    logging.basicConfig(level=logging.ERROR)
    config = load_config(args.config)
    intents = load_intents()
    cases = yaml.safe_load(args.eval.read_text())["cases"]
    names = (
        ["realtime_intent", "semantic_router"]
        if args.routers == "both"
        else [args.routers]
    )
    modes = ["text", "context"] if args.modes == "both" else [args.modes]
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "packages": versions(),
        "source_revisions": {
            "realtime_intent": revision(
                BASE / config["realtime_intent"]["upstream_path"]
            ),
            "semantic_router": revision(BASE / "../../semantic-router"),
        },
        "data_sha256": {
            "intents": sha256(BASE / "intent_data/intents.yaml"),
            "eval": sha256(args.eval),
        },
        "seed": args.seed,
        "repeat": args.repeat,
        "independent_eval_cases": len(cases),
        "concurrency": 1,
        "runs": {},
    }
    try:
        from models import LocalModels

        start = perf_counter()
        models = LocalModels(config["models"], reranker="realtime_intent" in names)
        report["model_load_ms"] = (perf_counter() - start) * 1000
        report["models"] = models.metadata()
    except Exception as e:
        report["model_load_error"] = f"{type(e).__name__}: {e}"
        write_report(args.output, report)
        raise
    failed = False
    for mode in modes:
        # Alternate router order to reduce fixed order bias; same seeded case sequence.
        for name in names if mode == "text" else list(reversed(names)):
            key = f"{name}/{mode}"
            router = None
            run = {}
            report["runs"][key] = run
            try:
                start = perf_counter()
                router = make_router(name, intents, models, config, mode == "context")
                run["index_init_ms"] = (perf_counter() - start) * 1000
                run["first_detect_ms"] = router.detect(
                    "模型预热：请问您是哪位"
                ).latency_ms
                router.detect("模型预热：授权通知已经收到了")
                order = [(r, c) for r in range(args.repeat) for c in cases]
                random.Random(args.seed).shuffle(order)
                rows = []
                run["rows"] = rows
                for j, (rep, case) in enumerate(order):
                    ctx = case.get("context", []) if mode == "context" else []
                    row = {**case, "context": ctx, "repeat": rep}
                    start = perf_counter()
                    try:
                        row.update(router.detect(case["text"], ctx).to_dict())
                        row["error"] = None
                    except Exception as e:
                        row.update(
                            intent_id=None,
                            score=None,
                            latency_ms=(perf_counter() - start) * 1000,
                            error=f"{type(e).__name__}: {e}",
                        )
                        failed = True
                    rows.append(row)
                    if j % 25 == 0:
                        print(f"{key}: {j + 1}/{len(order)}", flush=True)
                run["summary"] = summarize(rows)
            except Exception as e:
                run["error"] = f"{type(e).__name__}: {e}"
                failed = True
                print(f"{key}: {run['error']}", file=sys.stderr, flush=True)
            finally:
                if router is not None:
                    router.close()
                write_report(args.output, report)
    print(f"Report: {args.output}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
