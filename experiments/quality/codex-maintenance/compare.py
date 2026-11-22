"""Compare six finished Codex maintenance receipts. Positive savings mean less after."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from decimal import Decimal

from fixtures import TASKS

ARMS = ("before", "after")
COMMON = ("fixtures_sha256", "runner_sha256", "cli_sha256", "cli", "cli_options", "model", "timeout_seconds")
ARM_PINS = ("guide_sha256", "nex_sha256", "source_commit")
TOKENS = ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "total_tokens")
METRICS = (*TOKENS, "agent_ms", "end_to_end_ms")
DIGEST = re.compile(r"[0-9a-f]{64}")
CHECK_NAMES = {"queue-interface": ("visible", "held_out", "consumer")}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_count(value):
    return type(value) is int and value >= 0


def millisecond(seconds):
    require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0,
            "invalid duration")
    return int((Decimal(str(seconds)) * 1000).to_integral_value())


def signed_savings(before, after):
    if before is None or after is None:
        return {"saved": None, "percent": None}
    return {"saved": round(before - after, 3),
            "percent": round(100 * (before - after) / before, 3) if before else None}


def trial(row):
    require(row["schema"] == "nex.codex-maintenance/1" and row["status"] == "finished",
            "expected a finished maintenance receipt")
    require(row["unchanged_sdk"] is True, "SDK changed during a trial")
    for key in ("raw_sha256", "guide_sha256", "nex_sha256", "prompt_sha256",
                "fixtures_sha256", "runner_sha256", "cli_sha256"):
        require(isinstance(row[key], str) and DIGEST.fullmatch(row[key]), "invalid " + key)
    require(re.fullmatch(r"[0-9a-f]{40,64}", row["source_commit"]), "invalid source commit")
    require(re.fullmatch(r"[A-Za-z0-9._-]+", row["model"]), "unexpected model identifier")
    require(re.fullmatch(r"codex-cli [A-Za-z0-9.+_-]+", row["cli"]), "unexpected CLI version")
    require(is_count(row["timeout_seconds"]) and row["timeout_seconds"] > 0, "invalid timeout")
    require(isinstance(row["cli_options"], list) and all(isinstance(v, str) for v in row["cli_options"]),
            "invalid CLI options")
    arm, task = row["arm"], row["task"]
    require(arm in ARMS and task in TASKS, "unknown trial arm or task")
    starter = row["starter_sha256"]
    require(isinstance(starter, dict) and starter and all(
        re.fullmatch(r"[a-z_]+\.(nex|json)", name) and DIGEST.fullmatch(value)
        for name, value in starter.items()), "invalid starter file digest")
    require(type(row["accepted"]) is bool and type(row["complete_usage"]) is bool, "missing trial outcome")
    usage = row["usage"]
    metrics = dict.fromkeys(TOKENS)
    if row["complete_usage"]:
        require(isinstance(usage, dict) and all(is_count(usage.get(k)) for k in ("input_tokens", "output_tokens")),
                "usage marked complete without input/output counts")
        metrics["input_tokens"] = usage["input_tokens"]
        metrics["output_tokens"] = usage["output_tokens"]
        metrics["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
        cached = usage.get("cached_input_tokens")
        if cached is not None:
            require(is_count(cached) and cached <= usage["input_tokens"], "invalid cache accounting")
            metrics["cached_input_tokens"] = cached
            metrics["uncached_input_tokens"] = usage["input_tokens"] - cached
    else:
        require(usage is None, "ambiguous partial usage in maintenance/1")
    metrics["agent_ms"] = millisecond(row["agent_seconds"])
    metrics["end_to_end_ms"] = millisecond(row["end_to_end_seconds"])
    require(metrics["agent_ms"] <= metrics["end_to_end_ms"], "inconsistent duration")
    verification = row["acceptance"]
    require(type(verification["ok"]) is bool and type(row["timed_out"]) is bool and type(row["exit_code"]) is int,
            "invalid exit or verifier state")
    names = CHECK_NAMES.get(task, ("visible", "held_out"))
    checks = verification.get("checks", {})
    require(isinstance(checks, dict) and all(name in names for name in checks), "unexpected verifier checks")
    observed = {}
    for name, result in checks.items():
        require(type(result["ok"]) is bool, "invalid verifier check result")
        observed[name] = result["ok"]
        if result["ok"]:
            require(result.get("native") is True and result.get("exit") == 0, "check lacks native confirmation")
    require(verification["ok"] == all(observed.get(name) is True for name in names), "inconsistent verifier verdict")
    expected_acceptance = (verification["ok"] and not row["timed_out"] and row["exit_code"] == 0 and
                           row["events"].get("turn.completed") == 1 and not row["events"].get("turn.failed"))
    require(row["accepted"] == expected_acceptance, "inconsistent acceptance")
    return {"accepted": row["accepted"], "timed_out": row["timed_out"], "exit_code": row["exit_code"],
            "verifier_ok": verification["ok"], "checks_passed": observed, "metrics": metrics,
            "complete_usage": row["complete_usage"], "raw_sha256": row["raw_sha256"]}


def summary(trials):
    accepted = sum(t["accepted"] for t in trials)
    stats = {}
    for key in METRICS:
        available = [t["metrics"][key] for t in trials if t["metrics"][key] is not None]
        total = sum(available) if len(available) == len(trials) else None
        stats[key] = {"observed_trials": len(available), "known_sum": sum(available),
                      "total": total, "per_accepted": round(total / accepted, 3) if total is not None and accepted else None}
    return {"attempts": len(trials), "accepted": accepted,
            "verifier_passes": sum(t["verifier_ok"] for t in trials), "metrics": stats}


def compare(rows):
    matrix = {}
    by_arm = {arm: {} for arm in ARMS}
    for row in rows:
        result = trial(row)
        arm, task = row["arm"], row["task"]
        require((arm, task) not in matrix, "duplicate arm/task")
        matrix[arm, task] = row
        by_arm[arm][task] = result
    require(all(set(trials) == set(TASKS) for trials in by_arm.values()), "incomplete task matrix")
    first = matrix["before", next(iter(TASKS))]
    for row in matrix.values():
        for key in COMMON:
            require(row[key] == first[key], key + " differs between trials")
    identity = {k: first[k] for k in COMMON if k != "cli_options"}
    # Hash the exact settings instead of republishing paths or account-specific
    # values that a future launcher might include.
    identity["cli_options_sha256"] = hashlib.sha256(
        json.dumps(first["cli_options"], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    builds = {}
    for arm in ARMS:
        representative = matrix[arm, next(iter(TASKS))]
        for task in TASKS:
            require(all(matrix[arm, task][k] == representative[k] for k in ARM_PINS),
                    "guide, executable or source varied within " + arm)
        builds[arm] = {k: representative[k] for k in ARM_PINS}
    pairs = {}
    for task in TASKS:
        before, after = (matrix[arm, task] for arm in ARMS)
        for key in ("starter_sha256", "prompt_sha256"):
            require(before[key] == after[key], key + " differs for " + task)
        a, b = (by_arm[arm][task] for arm in ARMS)
        pairs[task] = {"prompt_sha256": before["prompt_sha256"], "starter_sha256": before["starter_sha256"],
                       "before": a, "after": b, "savings": {
                           k: signed_savings(a["metrics"][k], b["metrics"][k]) for k in METRICS}}
    summaries = {arm: summary(list(trials.values())) for arm, trials in by_arm.items()}
    savings = {key: {basis: signed_savings(*(summaries[arm]["metrics"][key][basis] for arm in ARMS))
                     for basis in ("total", "per_accepted")} for key in METRICS}
    return {"schema": "nex.codex-maintenance-comparison/1", "common": identity, "builds": builds,
            "tasks": pairs, "arms": summaries, "savings": savings, "currency_cost": None,
            "savings_definition": "before minus after; positive means lower after; cached input is part of input"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs=6)
    parser.add_argument("--output", type=Path, required=True, help="must be a new file")
    args = parser.parse_args()
    try:
        result = compare([json.loads(path.read_bytes()) for path in args.receipts])
        with args.output.open("x", encoding="utf-8") as out:
            out.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
