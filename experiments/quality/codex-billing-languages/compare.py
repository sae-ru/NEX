"""Summarize a balanced nine-slot cross-language repair experiment."""
import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import re


LANGUAGES = ("nex", "cpp", "python")
BLOCKS = tuple(LANGUAGES[i:] + LANGUAGES[:i] for i in range(3))
COMMON_PINS = ("base_prompt_sha256", "full_prompt_sha256", "cases_sha256", "settings_sha256", "runner_sha256")
LANGUAGE_PINS = ("starter_sha256", "toolchain_sha256")
TIMES = ("agent_seconds", "end_to_end_seconds")
TOKENS = ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens",
          "total_tokens", "uncached_input_plus_output")
METRICS = (*TIMES, *TOKENS)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(s):
    require(isinstance(s, str) and re.fullmatch("[0-9a-f]{64}", s), "invalid SHA256")
    return s


def count(x):
    require(type(x) is int and x >= 0, "invalid token count")
    return x


def time_value(x):
    require(type(x) in (float, int) and math.isfinite(x) and x >= 0, "invalid elapsed time")
    return x


def observed_usage(u):
    metrics = dict.fromkeys(TOKENS)
    if u is None:
        return metrics
    i, o = count(u["input_tokens"]), count(u["output_tokens"])
    metrics.update(input_tokens=i, output_tokens=o, total_tokens=i+o)
    c = u.get("cached_input_tokens")
    if c is not None:
        require(count(c) <= i, "cache exceeds input")
        metrics.update(cached_input_tokens=c, uncached_input_tokens=i-c, uncached_input_plus_output=i-c+o)
    return metrics


def trial(row):
    require(row["status"] == "finished" and type(row["accepted"]) is bool, "incomplete trial")
    verifier = row["acceptance"]
    require(isinstance(verifier, dict) and type(verifier["ok"]) is bool, "invalid acceptance")
    checks = {}
    for name, result in verifier.get("checks", {}).items():
        require(name in ("visible", "hidden", "held_out"), "unexpected verifier check")
        require(isinstance(result, dict) and type(result["ok"]) is bool, "invalid verifier check")
        if result["ok"] and "exit" in result:
            require(type(result["exit"]) is int and result["exit"] == 0, "passing check has failed exit")
        checks[name] = result["ok"]
    if checks or "checks" in verifier:
        passed = checks.get("visible") and (checks.get("hidden") or checks.get("held_out"))
        require(verifier["ok"] == bool(passed), "verdict does not match visible and held-out checks")
    successful = verifier["ok"] and not row.get("timed_out", False) and row.get("exit_code", 0) == 0
    if "events" in row:
        successful = successful and row["events"].get("turn.completed") == 1 and not row["events"].get("turn.failed")
    require(row["accepted"] == successful, "verdict does not match process and verifier")
    if "complete_usage" in row:
        require(row["complete_usage"] is (row["usage"] is not None), "usage coverage inconsistent")
    metrics = observed_usage(row["usage"])
    metrics.update({key: time_value(row[key]) for key in TIMES})
    require(metrics["agent_seconds"] <= metrics["end_to_end_seconds"], "invalid completion time")
    return {"language": row["language"], "block": row["block"], "position": row["position"],
            "accepted": row["accepted"], "verifier_passed": verifier["ok"],
            "checks": checks, "metrics": metrics, "raw_sha256": digest(row["raw_sha256"])}


def summarize(rows):
    successes = sum(r["accepted"] for r in rows)
    metrics = {}
    for key in METRICS:
        values = [r["metrics"][key] for r in rows if r["metrics"][key] is not None]
        observed = round(sum(values), 6)
        total = observed if len(values) == len(rows) else None
        metrics[key] = {"observed_trials": len(values), "observed_sum": observed, "total": total,
                        "per_accepted": round(total / successes, 6) if total is not None and successes else None}
    cached = metrics["cached_input_tokens"]["total"]
    all_input = metrics["input_tokens"]["total"]
    return {"attempts": len(rows), "accepted": successes, "metrics": metrics,
            "input_cache_share": round(cached / all_input, 6) if cached is not None and all_input else None}


def compare(rows):
    require(len(rows) == 9, "expected three blocks of three trials")
    common = {k: digest(rows[0][k]) for k in COMMON_PINS}
    model = rows[0]["model"]
    require(isinstance(model, str) and re.fullmatch("[A-Za-z0-9._-]+", model), "invalid model name")
    common["model"] = model
    slots, starts, pins = {}, {}, {}
    for row in rows:
        require(all(row[k] == v for k, v in common.items()), "common task or tool identity changed")
        b, p, lang = row["block"], row["position"], row["language"]
        require(type(b) is int and type(p) is int and 1 <= b <= 3 and 1 <= p <= 3 and BLOCKS[b-1][p-1] == lang,
                "language does not match position in balanced design")
        require((b,p) not in slots, "duplicate trial")
        t = trial(row)
        starts[b,p] = datetime.fromisoformat(row["started_utc"].replace("Z", "+00:00"))
        require(starts[b,p].utcoffset() == timedelta(0), "expected UTC trial start")
        ids = {k: digest(row[k]) for k in LANGUAGE_PINS}
        require(pins.setdefault(lang, ids) == ids, "language fixture or toolchain changed")
        slots[b,p] = t
    ordered = sorted(slots)
    for a, b in zip(ordered, ordered[1:]):
        dt = (starts[b] - starts[a]).total_seconds()
        require(dt > 0 and dt + .001 >= slots[a]["metrics"]["end_to_end_seconds"],
                "trial times inconsistent with sequential design")
    trials = [slots[k] for k in ordered]
    aggregates = {lang: summarize([r for r in trials if r["language"] == lang]) for lang in LANGUAGES}
    ratios = {}
    for lang in ("cpp", "python"):
        ratio = {}
        for key in METRICS:
            nex = aggregates["nex"]["metrics"][key]["per_accepted"]
            reference = aggregates[lang]["metrics"][key]["per_accepted"]
            ratio[key] = round(nex / reference, 6) if reference and nex is not None else None
        ratios["nex_over_" + lang] = ratio
    return {"schema": "nex.codex-billing-languages-comparison/1", "common": common, "language_pins": pins,
            "order": BLOCKS, "trials": trials, "languages": aggregates, "per_accepted_ratios": ratios,
            "unit": "All attempts, including failures, divided by number of accepted repairs in that language.",
            "ratio_unit": "NEX cost per accepted repair divided by the other language's cost per accepted repair.",
            "definition": "Total=input+output. Cache reads are part of input. Uncached input plus output "
                          "counts each once and excludes cached input; it does not represent a billed amount. "
                          "End-to-end includes independent acceptance.",
            "caveats": ["Three fresh sessions per language on one previously created defect.",
                        "Remote cache hits and wall time may vary with service load and run order."],
            "currency_cost": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs=9)
    parser.add_argument("--output", required=True, type=Path, help="new JSON summary")
    args = parser.parse_args()
    try:
        result = compare([json.loads(p.read_bytes()) for p in args.receipts])
        with args.output.open("x", encoding="utf-8") as target:
            target.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    except (IndexError, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
