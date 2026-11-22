"""Run nine independent Codex repairs of the same warehouse billing incident."""
import argparse
from datetime import datetime, timezone
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import compare
import cpp_fixture
import python_fixture

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "codex-multimodule"))
import fixture as shared
import run as prior
import project

pilot = prior.pilot
SOURCES = {"nex": shared.SOURCES, "cpp": cpp_fixture.SOURCES, "python": python_fixture.SOURCES}
PROMPT = b"""Repair the regression in this multi-module Depot Ledger checkout. The disputed
storage invoice currently returns 1252 cents; its contract requires 2079 cents.
Find the cause, fix the production code, preserve its interfaces and run ./test.
Read the local README and sources as needed. Do not change the tests, launcher,
manifest or specification. Work only in this project, without consulting other
directories, trials or the internet. Briefly summarize your fix and verification.
"""


def reference_change(language, constant):
    if language == "cpp" and not constant:
        return "availability.hpp", cpp_fixture.corrected_sources()["availability.hpp"]
    edits = {
        ("cpp", True): ("invoice.hpp", "sales, due};", "sales, 2079};"),
        ("python", True): ("invoice.py", "sales, due)", "sales, 2079)"),
        ("nex", True): ("invoice.nex", "sales, due);", "sales, 2079);"),
        ("python", False): ("availability.py", "frontier = event.stop", "frontier = max(frontier, event.stop)"),
        ("nex", False): ("availability.nex", "frontier = event.stop;", "if frontier < event.stop { frontier = event.stop; }"),
    }
    name, old, new = edits[language, constant]
    original = SOURCES[language][name]
    if original.count(old) != 1:
        raise ValueError("reference edit no longer matches " + name)
    return name, original.replace(old, new)


def controls(language, executable):
    with tempfile.TemporaryDirectory(prefix="depot-control-") as tmp:
        root = Path(tmp)
        project.create(root, language, executable)
        if not project.reproduction(root, language, executable):
            raise ValueError(language + " did not reproduce the disputed amounts")
        starter = project.verify(root, language, executable)
        name, fixed = reference_change(language, False)
        (root / name).write_text(fixed)
        repaired = project.verify(root, language, executable)
        (root / name).write_text(SOURCES[language][name])
        name, wrong = reference_change(language, True)
        (root / name).write_text(wrong)
        shortcut = project.verify(root, language, executable)
        if (any(x["ok"] for x in starter["checks"].values()) or not repaired["ok"]
                or not shortcut["checks"]["visible"]["ok"] or shortcut["checks"]["hidden"]["ok"]):
            raise ValueError("Unexpected control outcome " + str((language, starter, repaired, shortcut)))
        return {"starter": starter, "corrected": repaired, "constant_invoice": shortcut}


def identity(language, exe):
    if language == "nex":
        version = json.loads(subprocess.check_output([exe, "help", "test", "--json"]))["compiler"]["version"]
    else:
        version = subprocess.check_output([exe, "--version"], text=True).splitlines()[0]
    return {"version": version, "executable_sha256": pilot.digest(exe)}


def candidate_patch(root, language):
    lines = []
    for name, original in SOURCES[language].items():
        path = root / name
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536:
            candidate = path.read_text(errors="replace")
            lines.extend(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
                                              fromfile="a/" + name, tofile="b/" + name))
    return "".join(lines)


def trial(dest, language, executable, block, position, cli, env, protocol, timeout):
    dest.mkdir()
    target = dest / "result.json"
    with tempfile.TemporaryDirectory(prefix="depot-trial-") as directory:
        root = Path(directory) / "project"
        root.mkdir()
        project.create(root, language, executable)
        record = {**protocol["pins"], "schema": "nex.codex-billing-languages-trial/1",
                  "language": language, "block": block, "position": position,
                  "starter_sha256": prior.project_hash(root),
                  "toolchain_sha256": prior.canonical_digest(protocol["tools"][language]),
                  "full_prompt_sha256": pilot.sha(PROMPT), "status": "preparing",
                  "started_utc": datetime.now(timezone.utc).isoformat()}
        pilot.save(target, record)
        start = time.monotonic()
        if not project.reproduction(root, language, executable):
            raise RuntimeError("The starter no longer reproduces the incident")
        record["status"] = "running"
        pilot.save(target, record)
        raw = dest / "raw.jsonl"
        timed_out = False
        with raw.open("xb") as stdout, (dest / "stderr.log").open("xb") as stderr:
            agent_start = time.monotonic()
            proc = subprocess.Popen([cli, *prior.POLICY, "-C", str(root), "-"],
                                    cwd=root, env=env, stdin=subprocess.PIPE, stdout=stdout,
                                    stderr=stderr, start_new_session=True)
            try:
                proc.communicate(input=PROMPT, timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                pilot.stop(proc)
            except BaseException:
                pilot.stop(proc)
                raise
        agent_done = time.monotonic()
        usage = pilot.metering(raw)
        verified = project.verify(root, language, executable)
        finished = time.monotonic()
        patch = candidate_patch(root, language)
        (dest / "candidate.patch").write_text(patch)
        accepted = bool(verified["ok"] and not timed_out and proc.returncode == 0
                        and usage["events"].get("turn.completed") == 1 and not usage["events"].get("turn.failed"))
        record.update(usage, status="finished", accepted=accepted, acceptance=verified,
                      agent_seconds=round(agent_done-agent_start, 3),
                      end_to_end_seconds=round(finished-start, 3), exit_code=proc.returncode,
                      timed_out=timed_out, raw_sha256=pilot.digest(raw),
                      patch_sha256=pilot.sha(patch.encode()))
        pilot.save(target, record)
        print(block, position, language, "accepted", accepted, record["end_to_end_seconds"], usage["usage"], flush=True)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in compare.LANGUAGES:
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new ignored directory for private logs")
    parser.add_argument("--controls-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    os.umask(0o077)
    output = args.output.resolve()
    if output.is_relative_to(prior.ROOT) and subprocess.run(
            ["git", "check-ignore", "-q", "--", str(output / "raw.jsonl")], cwd=prior.ROOT).returncode:
        parser.error("use an ignored output directory")
    if output.exists():
        parser.error("use a fresh output directory")
    executables = {k: getattr(args, k).absolute() for k in compare.LANGUAGES}
    tool_ids = {k: identity(k, v) for k, v in executables.items()}
    output.mkdir(parents=True)
    checks = {k: controls(k, exe) for k, exe in executables.items()}
    pilot.save(output / "controls.json", checks)
    print("All three original, reference and constant-invoice controls passed.", flush=True)
    if args.controls_only:
        return
    env = {k: os.environ[k] for k in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "USER",
                                      "SHELL", "LOGNAME", "SYSTEMROOT") if k in os.environ}
    env["NO_COLOR"] = "1"
    cli = shutil.which("codex")
    auth = subprocess.run([cli, "login", "status"], env=env, capture_output=True, text=True, timeout=15)
    if auth.returncode or "Logged in using ChatGPT" not in auth.stdout + auth.stderr:
        parser.error("Codex must be logged in using ChatGPT")
    version = subprocess.check_output([cli, "--version"], env=env, text=True).strip()
    files = [Path(__file__), Path(project.__file__), Path(cpp_fixture.__file__), Path(python_fixture.__file__),
             Path(prior.__file__), Path(shared.__file__), Path(pilot.__file__), Path(compare.__file__)]
    pins = {"model": prior.MODEL, "base_prompt_sha256": pilot.sha(PROMPT),
            "cases_sha256": prior.canonical_digest([(c, shared.oracle(c)) for c in shared.CASES]),
            "settings_sha256": prior.canonical_digest([prior.POLICY, args.timeout, pilot.digest(cli)]),
            "runner_sha256": prior.canonical_digest({str(p.relative_to(prior.ROOT)): pilot.digest(p) for p in files})}
    protocol = {"pins": pins, "tools": tool_ids, "cli_version": version, "order": compare.BLOCKS,
                "timeout_seconds": args.timeout, "policy": prior.POLICY, "prompt": PROMPT.decode(),
                "source_base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=prior.ROOT, text=True).strip()}
    pilot.save(output / "protocol.json", protocol)
    receipts = []
    for block, order in enumerate(compare.BLOCKS, 1):
        for position, language in enumerate(order, 1):
            receipt = trial(output / f"b{block}-{position}-{language}", language, executables[language],
                            block, position, cli, env, protocol, args.timeout)
            receipts.append(receipt)
            if not receipt["events"].get("turn.completed") and not receipt["items_completed"]:
                raise RuntimeError("Service returned no completed work; inspect private logs before restarting")
    if tool_ids != {k: identity(k, v) for k, v in executables.items()}:
        raise RuntimeError("Toolchain changed during the experiment")
    pilot.save(output / "comparison.json", compare.compare(receipts))


if __name__ == "__main__":
    main()
