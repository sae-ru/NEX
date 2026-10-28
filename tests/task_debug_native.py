"""Opt-in compiled task debugging preserves source observations and code identity.

Live all-stop/LLDB/DAP/watch behavior is tested separately by task_debugging.py.
This gate executes actual images and checks compiler metadata/cache admission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

from task_profile_native import SCENARIOS, FAILURE
from task_migration import database_state

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("builder", type=Path)
    parser.add_argument("nex", type=Path)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    requested = options.output or (Path(os.environ["NEX_TASK_DEBUG_NATIVE_OUTPUT"])
                                  if os.environ.get("NEX_TASK_DEBUG_NATIVE_OUTPUT") else None)
    temporary = tempfile.TemporaryDirectory(prefix="nex task debug native ") if requested is None else None
    output = Path(temporary.name) if temporary else requested.resolve()
    if not temporary:
        output.mkdir(parents=True, exist_ok=False)
    work = output / "work"
    work.mkdir()
    (work / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.24", "entry": "calls.nex"}))
    grant = work / "grant"
    grant.mkdir()
    (grant / "text").write_bytes("A🧠\0B".encode())
    (grant / "bytes").write_bytes(b"A\0\xff")
    environment = dict(os.environ, NEX_FILES_ROOT=str(grant))
    for key in ("NEX_RESOURCE_DIR", "NEX_PROFILE_OUTPUT", "NEX_TRACY", "NEX_FILES_WRITE"):
        environment.pop(key, None)
    commands = []
    report = {"schema": "nex.task-debug-native-test/1", "ok": False,
              "scenarios": [], "live_debugger_claim": False, "general_provider_claim": False}

    def execute(command, cwd=work, expected=0, timeout=300):
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=environment,
                                capture_output=True, text=True, timeout=timeout)
        row = {"command": list(map(str, command)), "cwd": str(cwd), "exit": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr}
        commands.append(row)
        (output / "commands.json").write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n")
        assert result.returncode == expected, row
        return result

    def cli(*args, expected=0, cwd=work):
        return json.loads(execute([options.nex.resolve(), *args, "--json"], cwd=cwd, expected=expected).stdout)

    def build(source):
        return json.loads(execute([options.builder.resolve(), source, output / "artifact"]).stdout)

    def inspect(built, expected_names):
        manifest = json.loads(Path(built["debug_manifest"]).read_text())
        metadata = json.loads(Path(built["metadata"]).read_text())
        assert manifest["schema"] == "nex.debug/2" and manifest["language"] == "0.24", manifest
        assert manifest["revision"] == built["revision"] and manifest["build_key"] == built["build_key"], manifest
        assert manifest["runtime_view"] == "nex.runtime-view/3", manifest
        assert manifest["expression_protocol"] == "nex.task-debug-expression/1", manifest
        debug = manifest["task_debug"]
        assert debug["schema"] == "nex.task-debug-view/1" and debug["abi"] == 1, debug
        assert debug["catalog_symbol"] == "nex_task_debug_catalog_v1", debug
        assert debug["marker_symbol"] == "nex_task_debug_stop_marker", debug
        assert debug["deadline_advances_while_stopped"] is True, debug
        assert re.fullmatch("[0-9a-f]{64}", debug["metadata_hash"]), debug
        assert re.fullmatch("[0-9a-f]{32,64}", debug["image_uuid"]), debug
        assert hashlib.sha256(Path(built["executable"]).read_bytes()).hexdigest() == debug["image_sha256"], debug
        assert metadata["task_debug"] and metadata["runtime_requirements"]["task_debug"], metadata
        assert metadata["task_debug_metadata_hash"] == debug["metadata_hash"], metadata
        assert metadata["runtime_components"].count("nex_task_debug.cpp") == 1, metadata
        for resource in ("nex_task_debug.cpp", "nex_task_debug.h", "nex_task_debug_site.h"):
            assert resource in metadata["runtime_inputs"], resource
        functions = manifest["functions"]
        names = {f["name"] for f in functions}
        for name in expected_names:
            assert any(f.endswith("::" + name) for f in names), (name, names)
        assert len(names) == len(functions), names
        all_points = 0
        source_anchors = {s["debug_path"]: s["projection"] for s in manifest["sources"]}
        for code_index, function in enumerate(sorted(functions, key=lambda f: f["name"])):
            info = function["task_debug"]
            assert info["site_id"] == code_index + 1, info
            assert info["file"] in source_anchors and Path(source_anchors[info["file"]]).is_file(), info
            assert "source-anchors" in Path(info["file"]).parts, info
            assert function["function_hash"] and function["function_source_hash"], function
            assert function["task_continuation_symbol"].endswith("__task_step"), function
            bindings = info["bindings"]
            assert [b["id"] for b in bindings] == list(range(1, len(bindings) + 1)), bindings
            for binding in bindings:
                assert binding["scope"] >= 1 and binding["depth"] >= 0 and isinstance(binding["opaque"], bool), binding
                assert (binding["slot"] == -1 and binding["type"] == "unit") or 0 <= binding["slot"] < info["slot_count"], binding
                if binding["type"] == "task_scope" or binding["type"].startswith(("task<", "channel<")):
                    assert binding["opaque"], binding
            points = info["points"]
            assert points and points[0]["phase"] == "entry", points
            assert [p["id"] for p in points] == list(range(1, len(points) + 1)), points
            phases = ("entry", "statement", "loop_test", "call_entry", "resume", "return")
            ids = {b["id"] for b in bindings}
            for point in points:
                assert point["phase"] == phases[point["kind"]], point
                assert point["pc"] >= 0 and point["line"] >= 1 and point["column"] >= 1, point
                assert 0 <= point["begin"] <= point["end"], point
                assert re.fullmatch("[0-9a-f]{64}", point["site"]), point
                assert len(point["visible"]) == len(set(point["visible"])) and set(point["visible"]) <= ids, point
            all_points += len(points)
        llvm = Path(built["llvm"]).read_text()
        assert llvm.count("call void @nex_task_debug_prepare(") == 1, "missing single coordinator registry prepare"
        assert llvm.count("call void @nex_task_debug_checkpoint(") == all_points, (all_points, llvm)
        assert all_points <= debug["maximum_points"] and len(functions) <= debug["maximum_codes"], debug
        return manifest, metadata

    try:
        descriptor = cli("describe")
        assert descriptor["version"] == "0.24", descriptor
        for name, body, expected, stdout in SCENARIOS:
            source = work / (name + ".nex")
            source.write_text("module task_native_debug;\n" + body)
            reference = cli("eval", source)
            ordinary = cli("run", source, "--profile", "release")
            built = build(source)
            assert built["ok"] and not built["cached"], built
            instrumented = execute([built["executable"]], timeout=60)
            assert reference["stdout"] == ordinary["stdout"] == instrumented.stdout == stdout, (name, reference, ordinary, instrumented)
            assert not instrumented.stderr, instrumented
            manifest, metadata = inspect(built, expected)
            if name == "calls":
                # Instrumentation is a separate cache/runtime input; ordinary
                # debug builds keep the existing debug1 image and no catalog.
                default = cli("build", source, "--profile", "debug")
                default_info = json.loads((Path(default["executable"]).parent / "build.json").read_text())
                default_debug = json.loads((Path(default["executable"]).parent / "debug.json").read_text())
                assert not default_info["task_debug"] and not default_info["runtime_requirements"]["task_debug"], default_info
                assert "nex_task_debug.cpp" not in default_info["runtime_components"], default_info
                assert default_debug["schema"] == "nex.debug/1" and "task_debug" not in default_debug, default_debug
                assert "nex_task_debug_checkpoint" not in Path(default["llvm"]).read_text(), default
                assert default["build_key"] != built["build_key"], default
                warm = build(source)
                assert warm["cached"] and warm["build_key"] == built["build_key"], warm
                before = json.loads(Path(built["debug_manifest"]).read_text())
                (output / "original-cache-manifest.json").write_text(json.dumps(before, indent=2) + "\n")
                corrupt = json.loads(json.dumps(before))
                corrupt["functions"][0]["task_debug"]["points"][0]["visible"] = [999999]
                Path(built["debug_manifest"]).write_text(json.dumps(corrupt))
                repaired = build(source)
                assert not repaired["cached"] and repaired["build_key"] == built["build_key"], repaired
                repaired_manifest, _ = inspect(repaired, expected)
                # Relinking may refresh platform image UUID/SHA. Every checked
                # source/visibility field must remain identical.
                original_identity = before["task_debug"].copy()
                repaired_identity = repaired_manifest["task_debug"].copy()
                for field in ("image_sha256", "image_uuid"):
                    original_identity.pop(field)
                    repaired_identity.pop(field)
                assert original_identity == repaired_identity
                before["task_debug"] = original_identity
                repaired_manifest["task_debug"] = repaired_identity
                assert before == repaired_manifest
                Path(repaired["executable"]).write_bytes(Path(repaired["executable"]).read_bytes() + b"corrupt task debug cache")
                refreshed = build(source)
                assert not refreshed["cached"], refreshed
                inspect(refreshed, expected)
                assert execute([refreshed["executable"]], timeout=60).stdout == stdout
                report["opt_in_cache_and_metadata_image_repair"] = True
            report["scenarios"].append(name)

        # Imports retain their own frozen source anchors. Unreachable task code
        # is excluded from both the compiled image and debug registry.
        (work / "helper.nex").write_text("module debug_helper;pub fn value(n:i64)->i64 !{task}{task_yield();return n+1;}pub fn unreachable()->unit !{task}{assert(false);}")
        source = work / "modules.nex"
        source.write_text('module debug_modules;import "./helper.nex" as helper;fn main()->unit !{task,io}{print(helper::value(41));}')
        assert cli("eval", source)["stdout"] == cli("run", source, "--profile", "release")["stdout"] == "42\n"
        built = build(source)
        assert execute([built["executable"]], timeout=60).stdout == "42\n"
        manifest, _ = inspect(built, {"main", "value"})
        assert not any(f["name"].endswith("::unreachable") for f in manifest["functions"])
        assert len({f["task_debug"]["file"] for f in manifest["functions"]}) == 2, manifest
        report["scenarios"].append("module_source_identity")

        source = work / "failure.nex"
        source.write_text("module task_native_debug;\n" + FAILURE)
        reference = cli("eval", source, expected=1)
        ordinary = cli("run", source, "--profile", "release", expected=70)
        built = build(source)
        inspect(built, {"main", "task_leaf", "leaf"})
        failed = execute([built["executable"]], expected=70, timeout=60)
        assert reference["code"] == "E_DIV_ZERO" and "E_DIV_ZERO" in json.dumps(ordinary) and "E_DIV_ZERO" in failed.stderr
        assert reference["stdout"] == ordinary["stdout"] == failed.stdout == "before trap\n", (reference, ordinary, failed)
        report["scenarios"].append("trap_cleanup")

        fixture_path = REPO / "tests/fixtures/language-0.19-sdk115-tasks.json"
        fixture = json.loads(fixture_path.read_text())
        sql = fixture_path.with_suffix(".sql").read_bytes()
        assert hashlib.sha256(sql).hexdigest() == fixture["sql_sha256"] == "135e47e4f6de69a9e0035d071a740d58e11d88ae361144e399f04cf334724a98"
        historical = output / "genuine019"
        (historical / ".nex").mkdir(parents=True)
        database = historical / ".nex/graph.db"
        with sqlite3.connect(database) as db:
            db.executescript(sql.decode())
        row = fixture["revisions"][-1]
        for name, text in row["bundle"]["files"].items():
            (historical / name).write_text(text)
        for name, text in fixture["physical_files"].items():
            (historical / name).write_text(text)
        before = database_state(database)
        physical = {path: path.read_bytes() for path in historical.glob("*") if path.is_file()}
        raw_database = database.read_bytes()
        assert len(before["tables"]) == 16 and {k: len(v) for k, v in before["tables"].items()} == fixture["tables"]
        rejected = cli("debug", cwd=historical, expected=1)
        assert rejected["code"] == "E_LANGUAGE_VERSION", rejected
        assert database_state(database) == before and database.read_bytes() == raw_database
        assert all(path.read_bytes() == raw for path, raw in physical.items())
        report["genuine019_cli_rejected_all16_tables_ddl_head_and_physical_bytes_unchanged"] = True
        report["ok"] = True
    finally:
        report["commands"] = len(commands)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
