#!/usr/bin/env python3
"""Run the SOP controller evaluation against an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "data" / "drafts" / "cases_v0.1.jsonl"
DEFAULT_PROMPT = ROOT / "prompts" / "controller-v0.1.txt"
DEFAULT_RESULTS = ROOT / "results"


@dataclass(frozen=True)
class EndpointConfig:
    name: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    retries: int
    temperature: float
    max_tokens: int
    extra_body: dict[str, Any]


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


def resolve_endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


def render_prompt(template: str, case_input: dict[str, Any]) -> str:
    rendered = template
    for key in ("dialogue_state", "history", "user_text", "candidate_sops"):
        value = json.dumps(case_input[key], ensure_ascii=False, separators=(",", ":"))
        rendered = rendered.replace("{{" + key + "}}", value)
    if re.search(r"{{[^{}]+}}", rendered):
        raise ValueError("prompt contains unresolved template variables")
    return rendered


def parse_output(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    candidates = [raw.strip()]
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value, None
    return None, "response is not a JSON object"


def validate_output(output: dict[str, Any] | None) -> list[str]:
    if output is None:
        return ["invalid_json"]
    errors: list[str] = []
    if set(output) != {"sop_id", "detail"}:
        errors.append("invalid_keys")
    if not isinstance(output.get("sop_id"), str) or not output.get("sop_id"):
        errors.append("invalid_sop_id")
    detail = output.get("detail")
    if not isinstance(detail, str) or not detail or len(detail) > 50:
        errors.append("invalid_detail")
    return errors


def extract_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("response has no choices[0].message.content") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    raise ValueError("message content is not text")


def request_completion(config: EndpointConfig, prompt: str) -> tuple[str, float, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    payload.update(config.extra_body)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    last_error: Exception | None = None
    for attempt in range(config.retries + 1):
        request = urllib.request.Request(
            resolve_endpoint(config.base_url), data=body, headers=headers, method="POST"
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
            latency_ms = (time.perf_counter() - started) * 1000
            decoded = json.loads(response_body)
            return extract_content(decoded), latency_ms, decoded.get("usage", {})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < config.retries:
                time.sleep(min(2**attempt, 4))
    assert last_error is not None
    raise last_error


def score_case(case: dict[str, Any], raw: str) -> dict[str, Any]:
    parsed, parse_error = parse_output(raw)
    validation_errors = validate_output(parsed)
    candidate_ids = {item["id"] for item in case["input"]["candidate_sops"]}
    acceptable_ids = set(case["expected"]["acceptable_sop_ids"])
    sop_id = parsed.get("sop_id") if parsed else None
    return {
        "parsed_output": parsed,
        "parse_error": parse_error,
        "validation_errors": validation_errors,
        "json_valid": not validation_errors,
        "candidate_valid": isinstance(sop_id, str) and sop_id in candidate_ids,
        "sop_correct": isinstance(sop_id, str) and sop_id in acceptable_ids,
        "manual_detail_review_required": True,
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 2)


def summarize(results: list[dict[str, Any]], config: EndpointConfig) -> dict[str, Any]:
    completed = [row for row in results if row["error"] is None]
    latencies = [row["latency_ms"] for row in completed]

    def count(field: str) -> int:
        return sum(bool(row.get(field)) for row in completed)

    denominator = len(completed)
    return {
        "run_name": config.name,
        "model": config.model,
        "base_url": config.base_url,
        "total_cases": len(results),
        "completed_cases": denominator,
        "failed_requests": len(results) - denominator,
        "json_valid_count": count("json_valid"),
        "json_valid_rate": round(count("json_valid") / denominator, 4) if denominator else None,
        "candidate_valid_count": count("candidate_valid"),
        "candidate_valid_rate": round(count("candidate_valid") / denominator, 4) if denominator else None,
        "sop_correct_count": count("sop_correct"),
        "sop_accuracy": round(count("sop_correct") / denominator, 4) if denominator else None,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 2) if latencies else None,
        },
        "note": "detail semantic requirements still require manual review",
    }


def load_profile(path: Path) -> dict[str, Any]:
    profile = load_json(path)
    base_url = profile.get("base_url")
    if not base_url and profile.get("base_url_env"):
        base_url = os.getenv(profile["base_url_env"])
    if not base_url:
        raise ValueError("profile must set base_url or a populated base_url_env")

    api_key = profile.get("api_key", "")
    if profile.get("api_key_env"):
        api_key = os.getenv(profile["api_key_env"], "")
        if not api_key:
            raise ValueError(f"environment variable {profile['api_key_env']} is not set")
    return {**profile, "base_url": base_url, "api_key": api_key}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = load_profile(args.profile)
    config = EndpointConfig(
        name=profile.get("name", args.profile.stem),
        base_url=profile["base_url"],
        model=profile["model"],
        api_key=profile.get("api_key", ""),
        timeout_seconds=float(profile.get("timeout_seconds", 60)),
        retries=int(profile.get("retries", 2)),
        temperature=float(profile.get("temperature", 0)),
        max_tokens=int(profile.get("max_tokens", 128)),
        extra_body=profile.get("extra_body", {}),
    )
    cases = load_jsonl(args.cases)
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["case_id"] in selected]
        missing = selected - {case["case_id"] for case in cases}
        if missing:
            raise ValueError(f"unknown case ids: {', '.join(sorted(missing))}")
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise ValueError("no cases selected")

    template = args.prompt.read_text(encoding="utf-8")
    if args.dry_run:
        print(render_prompt(template, cases[0]["input"]))
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.results_dir / f"{config.name}-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    results_path = run_dir / "results.jsonl"
    results: list[dict[str, Any]] = []

    with results_path.open("w", encoding="utf-8") as output:
        for index, case in enumerate(cases, 1):
            row: dict[str, Any] = {
                "case_id": case["case_id"],
                "group_id": case["group_id"],
                "model": config.model,
                "raw_output": None,
                "latency_ms": None,
                "usage": {},
                "error": None,
                "json_valid": False,
                "candidate_valid": False,
                "sop_correct": False,
            }
            try:
                prompt = render_prompt(template, case["input"])
                raw, latency_ms, usage = request_completion(config, prompt)
                row.update({"raw_output": raw, "latency_ms": round(latency_ms, 2), "usage": usage})
                row.update(score_case(case, raw))
            except Exception as exc:  # Keep the batch and its evidence even if one call fails.
                row["error"] = f"{type(exc).__name__}: {exc}"
            results.append(row)
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            status = "ok" if row["error"] is None else "error"
            print(f"[{index}/{len(cases)}] {case['case_id']}: {status}", file=sys.stderr)

    summary = summarize(results, config)
    summary.update(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cases_path": str(args.cases),
            "prompt_path": str(args.prompt),
            "results_path": str(results_path),
        }
    )
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_requests"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
