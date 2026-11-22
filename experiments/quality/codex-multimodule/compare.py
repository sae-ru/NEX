"""Report paired descriptive contrasts for the eight Codex repair trials."""
import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import re

ORDER = ("old", "both", "context", "diagnostic")
BLOCKS = (ORDER, tuple(reversed(ORDER)))
PINS = ("prompt_sha256", "fixture_sha256", "starter_sha256", "runner_sha256", "settings_sha256",
        "old_sha256", "new_sha256", "cli_sha256", "pilot_runner_sha256")
TOKENS = ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "total_tokens")
METRICS = (*TOKENS, "agent_seconds", "end_to_end_seconds")
CONTRASTS = {
    "context_without_diagnostic": (("old",), ("context",)),
    "context_with_diagnostic": (("diagnostic",), ("both",)),
    "diagnostic_without_context": (("old",), ("diagnostic",)),
    "diagnostic_with_context": (("context",), ("both",)),
    "both_vs_old": (("old",), ("both",)),
    "context_main_effect": (("old", "diagnostic"), ("context", "both")),
    "diagnostic_main_effect": (("old", "context"), ("diagnostic", "both")),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    require(isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value), "invalid SHA-256")
    return value


def count(value):
    require(type(value) is int and value >= 0, "invalid count")
    return value


def seconds(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid time")
    return value


def complete_mean(values):
    return None if any(v is None for v in values) else sum(values) / len(values)


def trial(row):
    accepted = row["accepted"]
    require(type(accepted) is bool, "missing acceptance")
    require(row["schema"] == "nex.codex-multimodule/1" and row["status"] == "finished", "unfinished or wrong receipt")
    require(row["unchanged_sdks"] is True, "SDK changed during trial")
    require(type(row["timed_out"]) is bool and type(row["exit_code"]) is int, "invalid exit status")
    verifier = row["acceptance"]
    require(type(verifier["ok"]) is bool, "invalid verifier verdict")
    checks = verifier.get("checks", {})
    require(isinstance(checks, dict) and set(checks) <= {"visible", "hidden"}, "unexpected checks")
    for sub in checks.values():
        require(type(sub["ok"]) is bool, "invalid native verifier result")
        require(not sub["ok"] or (type(sub.get("exit")) is int and sub["exit"] == 0),
                "passing native verifier check requires a successful exit")
    checks_pass = all(checks.get(name, {}).get("ok") is True for name in ("visible", "hidden"))
    require(checks_pass == verifier["ok"], "inconsistent verifier verdict")
    finished = row["events"].get("turn.completed", 0) == 1 and not row["events"].get("turn.failed", 0)
    require(accepted == (checks_pass and finished and not row["timed_out"] and row["exit_code"] == 0),
            "inconsistent trial acceptance")
    usage = row["usage"]
    require(type(row["complete_usage"]) is bool and row["complete_usage"] == (usage is not None) and
            (usage is None or finished), "inconsistent metering")
    metrics = dict.fromkeys(TOKENS)
    if usage is not None:
        i, o = count(usage["input_tokens"]), count(usage["output_tokens"])
        metrics.update(input_tokens=i, output_tokens=o, total_tokens=i + o)
        c = usage.get("cached_input_tokens")
        if c is not None:
            require(count(c) <= i, "cached input exceeds total input")
            metrics.update(cached_input_tokens=c, uncached_input_tokens=i-c)
    for k in ("agent_seconds", "end_to_end_seconds"):
        metrics[k] = seconds(row[k])
    require(metrics["end_to_end_seconds"] >= metrics["agent_seconds"], "agent time exceeds end-to-end time")
    result = {"accepted": accepted, "metrics": metrics, "block": row["block"], "position": row["position"],
              "arm": row["arm"], "exposure": {k: count(row["exposure"][k])
                                               for k in ("context_bytes", "diagnostic_bytes")}}
    result["checks"] = {name: item["ok"] for name, item in checks.items()}
    result["complete_usage"] = row["complete_usage"]
    for key in ("raw_sha256", "context_sha256", "diagnostic_sha256", "full_prompt_sha256"):
        result[key] = sha(row[key])
    return result


def effects(means):
    out = {}
    for name, (without, with_feature) in CONTRASTS.items():
        group = {}
        for k in METRICS:
            before = complete_mean([means[a][k] for a in without])
            after = complete_mean([means[a][k] for a in with_feature])
            delta = None if before is None or after is None else before - after
            group[k] = {"saved": round(delta, 6) if delta is not None else None,
                        "percent": round(100 * delta / before, 4) if delta is not None and before else None}
        out[name] = group
    interaction = {}
    for k in METRICS:
        a, b, c, d = (means[arm][k] for arm in ("old", "context", "diagnostic", "both"))
        interaction[k] = None if None in (a, b, c, d) else round(b+c-a-d, 6)
    out["interaction_extra_saved"] = interaction
    return out


def compare(rows):
    require(len(rows) == 8, "exactly eight trials required")
    slots = {}
    common = {k: sha(rows[0][k]) for k in PINS}
    common["model"] = rows[0]["model"]
    require(isinstance(common["model"], str) and re.fullmatch(r"[a-zA-Z0-9._-]+", common["model"]),
            "unexpected model identifier")
    require(common["old_sha256"] != common["new_sha256"], "old and new compiler hashes match")
    common["source_commit"] = rows[0]["source_commit"]
    require(isinstance(common["source_commit"], str) and re.fullmatch("[a-f0-9]{40,64}", common["source_commit"]),
            "invalid source commit")
    common["cli_version"] = rows[0]["cli_version"]
    require(isinstance(common["cli_version"], str) and re.fullmatch(r"codex-cli [A-Za-z0-9.+_-]+", common["cli_version"]),
            "unexpected CLI version")
    common["timeout_seconds"] = count(rows[0]["timeout_seconds"])
    require(common["timeout_seconds"] > 0, "invalid timeout")
    feature_payloads, prompt_per_arm, starts = {}, {}, {}
    for row in rows:
        require(all(row[k] == val for k, val in common.items()), "inconsistent model or benchmark pins")
        b, p, arm = row["block"], row["position"], row["arm"]
        require(type(b) is int and type(p) is int and b in (1, 2) and 1 <= p <= 4 and
                BLOCKS[b-1][p-1] == arm, "arm differs from fixed position in block")
        require((b, p) not in slots, "duplicate slot")
        t = trial(row)
        for feature in ("context", "diagnostic"):
            key = (feature, arm in (feature, "both"))
            payload = (t["exposure"][feature + "_bytes"], t.get(feature + "_sha256"))
            require(feature_payloads.setdefault(key, payload) == payload, "inconsistent " + feature + " packet")
        if "full_prompt_sha256" in t:
            require(prompt_per_arm.setdefault(arm, t["full_prompt_sha256"]) == t["full_prompt_sha256"],
                    "full prompt changed across same-arm trials")
        stamp = datetime.fromisoformat(row["started_utc"])
        require(stamp.utcoffset() == timedelta(0), "expected UTC trial start")
        starts[b, p] = stamp
        slots[b, p] = t
    for feature in ("context", "diagnostic"):
        require(feature_payloads[feature, True][1] != feature_payloads[feature, False][1],
                feature + " treatment has identical packets")
        require(min(feature_payloads[feature, on][0] for on in (True, False)) > 0, "empty " + feature + " packet")
    ordered = [slots[k] for k in sorted(slots)]
    chronology = [starts[k] for k in sorted(slots)]
    for i, (first, second) in enumerate(zip(chronology, chronology[1:])):
        elapsed = (second - first).total_seconds()
        require(elapsed > 0 and elapsed + .001 >= ordered[i]["metrics"]["end_to_end_seconds"],
                "launch times do not follow the serial counterbalanced order")
    summaries, means = {}, {}
    for arm in ORDER:
        acts = [t for t in ordered if t["arm"] == arm]
        accepted = sum(t["accepted"] for t in acts)
        info = {}
        for k in METRICS:
            vals = [t["metrics"][k] for t in acts]
            known = [v for v in vals if v is not None]
            total = sum(known) if len(known) == len(vals) else None
            info[k] = {"observed": len(known), "observed_sum": round(sum(known), 6), "mean": complete_mean(vals),
                       "per_accepted": round(total / accepted, 6) if accepted and total is not None else None}
        summaries[arm] = {"accepted": accepted, "attempts": len(acts), "metrics": info}
        means[arm] = {k: info[k]["mean"] for k in METRICS}
    block_effects = [effects({t["arm"]: t["metrics"] for t in ordered if t["block"] == b})
                     for b in (1, 2)]
    return {"schema": "nex.codex-multimodule-comparison/1", "common": common,
            "design": "Two blocks on one defect in forward and reversed fixed order; fresh sessions.",
            "cost_unit": "Per attempt, including failed attempts. Per accepted divides all observed costs by successes.",
            "effect_unit": "Per-attempt marginal mean cost without minus with feature; positive is saving. "
                           "Interaction is extra saving from both relative to additive individual savings.",
            "caveats": ["Input includes cached input; reasoning output is included in output.",
                        "Wall time includes variable service latency and cache warmup.",
                        "Two repetitions of one task provide descriptive, workload-specific results."],
            "all_accepted": all(t["accepted"] for t in ordered), "currency_cost": None,
            "trials": ordered, "arms": summaries, "effects": effects(means),
            "effects_by_block": {"1": block_effects[0], "2": block_effects[1]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs=8)
    parser.add_argument("--output", required=True, type=Path, help="new shareable JSON file")
    args = parser.parse_args()
    try:
        report = compare([json.loads(p.read_bytes()) for p in args.receipts])
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        with args.output.open("x", encoding="utf-8") as f:
            f.write(encoded + "\n")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
