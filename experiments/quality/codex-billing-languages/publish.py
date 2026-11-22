"""Verify a finished private Depot Ledger campaign and export its public evidence."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re

import campaign
import compare


def load(path):
    return json.loads(path.read_bytes())


def checked_text(value, pattern):
    compare.require(isinstance(value, str) and re.fullmatch(pattern, value), "unexpected public text field")
    return value


def grade(data, language):
    result = {"ok": data["ok"]}
    compare.require(type(result["ok"]) is bool, "invalid grade")
    names = campaign.SOURCES[language]
    if "reason" in data:
        compare.require(not result["ok"] and data["reason"] in ("protected input changed", "invalid source"),
                        "unexpected rejection")
        result["reason"] = data["reason"]
        result["file"] = checked_text(data["file"], r"[a-zA-Z_]+(?:\.[a-z]+)?")
        return result
    changed = data["changed_modules"]
    compare.require(isinstance(changed, list) and len(changed) == len(set(changed))
                    and all(name in names for name in changed), "unexpected changed module")
    compare.require(data["held_out_cases"] == len(campaign.shared.CASES) - 1, "held-out case count changed")
    checks = {}
    for name in ("visible", "hidden"):
        item = data["checks"][name]
        compare.require(type(item["ok"]) is bool, "invalid verifier check")
        checks[name] = {"ok": item["ok"]}
        if "exit" in item:
            compare.require(type(item["exit"]) is int, "invalid verifier exit")
            checks[name]["exit"] = item["exit"]
        if item.get("code") is not None:
            checks[name]["code"] = checked_text(item["code"], r"[A-Z][A-Z_0-9]{0,63}")
    compare.require(result["ok"] == all(item["ok"] for item in checks.values()), "inconsistent grade")
    return dict(result, changed_modules=changed, held_out_cases=data["held_out_cases"], checks=checks)


def public_protocol(data, summary):
    pins = {k: summary["common"][k] for k in ("model", "base_prompt_sha256", "cases_sha256", "runner_sha256",
                                              "settings_sha256")}
    compare.require(pins == data["pins"] and data["order"] == [list(b) for b in compare.BLOCKS],
                    "protocol does not match receipts")
    prompt = campaign.PROMPT
    compare.require(data["prompt"].encode() == prompt and
                    campaign.pilot.sha(prompt) == pins["base_prompt_sha256"] == summary["common"]["full_prompt_sha256"],
                    "prompt does not match receipts")
    compare.require(data["policy"] == campaign.prior.POLICY, "unexpected CLI policy")
    compare.require(compare.count(data["timeout_seconds"]) > 0, "invalid timeout")
    tools = {}
    for lang in compare.LANGUAGES:
        tool = data["tools"][lang]
        tools[lang] = {"executable_sha256": compare.digest(tool["executable_sha256"]),
                       "version": checked_text(tool["version"], r"[a-zA-Z0-9][a-zA-Z0-9+_()., =:\-]{0,180}")}
        compare.require(campaign.prior.canonical_digest(tools[lang]) == summary["language_pins"][lang]["toolchain_sha256"],
                        "toolchain does not match receipts")
    return dict(pins=pins, tools=tools, policy=data["policy"], timeout_seconds=data["timeout_seconds"],
                order=compare.BLOCKS, prompt=data["prompt"], source_base=checked_text(data["source_base"], "[0-9a-f]{40}"),
                cli_version=checked_text(data["cli_version"], r"[a-zA-Z0-9][a-zA-Z0-9+._ \-]{0,80}"))


def public_patch(path, sha, changed):
    patch = path.read_bytes()
    compare.require(campaign.pilot.sha(patch) == sha, "candidate patch digest mismatch")
    value = patch.decode("utf-8")
    files = []
    for line in value.splitlines():
        if line.startswith("--- a/"):
            files.append(line[6:])
    compare.require(sorted(files) == sorted(changed), "candidate patch and verifier modules differ")
    # Source diffs are the only model-authored text exported. Withhold the report
    # for review if a candidate includes machine paths, addresses or credentials.
    private = r"(?i)(?:/(?:Users|home|private|tmp|var|mnt|Volumes)/|[a-z]:[\\/]|https?://|[\w.+-]+@[\w.-]+\.[a-z]{2,}|-----BEGIN|\b(?:sk-|gh[pousr]_|github_pat_)[a-zA-Z0-9_-]{12,})"
    compare.require(not re.search(private, value), "selected patch requires manual privacy review")
    return value


def publish(folder):
    paths = sorted(folder.glob("b*-*-*/result.json"))
    receipts = [load(p) for p in paths]
    summary = compare.compare(receipts)
    # A JSON round trip normalizes tuple orders to the arrays saved by the controller.
    compare.require(json.loads(json.dumps(summary)) == load(folder / "comparison.json"), "saved comparison mismatch")
    protocol = public_protocol(load(folder / "protocol.json"), summary)
    controls = {}
    inputs = load(folder / "controls.json")
    for lang in compare.LANGUAGES:
        controls[lang] = grades = {k: grade(inputs[lang][k], lang) for k in ("starter", "corrected", "constant_invoice")}
        for name, visible, hidden in (("starter", False, False), ("corrected", True, True), ("constant_invoice", True, False)):
            checks = grades[name]["checks"]
            compare.require(checks["visible"]["ok"] == visible and checks["hidden"]["ok"] == hidden,
                            "unexpected control outcome")
    rows, selected = [], {}
    for path, row in zip(paths, receipts):
        lang = row["language"]
        expected = f"b{row['block']}-{row['position']}-{lang}"
        compare.require(path.parent.name == expected, "trial directory does not match receipt")
        raw = path.with_name("raw.jsonl")
        compare.require(campaign.pilot.digest(raw) == row["raw_sha256"], "raw transcript digest mismatch")
        measured = campaign.pilot.metering(raw)
        compare.require(all(row[k] == value for k, value in measured.items()), "raw usage does not match receipt")
        patch = path.with_name("candidate.patch")
        compare.require(campaign.pilot.digest(patch) == row["patch_sha256"], "candidate patch digest mismatch")
        public = {k: row[k] for k in (*compare.COMMON_PINS, *compare.LANGUAGE_PINS, "model", "language", "block",
                                        "position", "accepted", "status", "complete_usage", "raw_sha256", "patch_sha256",
                                        "currency_cost", "provider_calls", "agent_seconds", "end_to_end_seconds")}
        compare.require(row["schema"] == "nex.codex-billing-languages-trial/1", "unexpected trial schema")
        public["schema"] = row["schema"]
        public["started_utc"] = datetime.fromisoformat(row["started_utc"].replace("Z", "+00:00")).isoformat()
        for key in ("timed_out", "exit_code", "malformed_events"):
            compare.require(type(row[key]) is (bool if key == "timed_out" else int), "invalid process metadata")
            public[key] = row[key]
        public["usage"] = None if row["usage"] is None else {k: row["usage"][k] for k in (
            "input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens",
            "reasoning_output_tokens") if k in row["usage"]}
        public["events"] = {k: row["events"][k] for k in ("thread.started", "turn.started", "turn.completed",
                            "turn.failed", "item.started", "item.completed", "error") if k in row["events"]}
        public["items_completed"] = {k: row["items_completed"][k] for k in ("agent_message", "command_execution",
                                     "file_change", "reasoning") if k in row["items_completed"]}
        public["acceptance"] = grade(row["acceptance"], lang)
        rows.append(public)
        if row["accepted"] and lang not in selected:
            selected[lang] = {"block": row["block"], "position": row["position"], "sha256": row["patch_sha256"],
                              "patch": public_patch(patch, row["patch_sha256"], public["acceptance"]["changed_modules"])}
    compare.require(compare.compare(rows) == summary, "public receipts do not reproduce comparison")
    return {"schema": "nex.codex-billing-languages-public/1", "protocol": protocol, "controls": controls,
            "receipts": rows, "comparison": summary, "first_accepted_patches": selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        evidence = publish(args.input)
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(evidence, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.write("\n")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
