"""Compiled source call accounting; AST/native observations remain independent."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


SCENARIOS = [
    ("calls", r'''
fn identity<T>(value:T)->T{return value;}
fn pure(value:i64)->i64{return identity(value)+1;}
fn recurse(n:i64)->i64 !{task}{task_yield();if n==0{return pure(0);}return recurse(n-1)+1;}
fn child(n:i64)->i64 !{task}{var i:i64=0;while i<7{task_yield();i=i+1;}return pure(n);}
fn keep(f:fn(i64)->i64 !{task})->(fn(i64)->i64 !{task}){return f;}
fn unused()->unit{assert(false);}
fn main()->unit !{task,io}{let indirect:fn(i64)->i64 !{task}=keep(child);print(child(10));print(indirect(20));print(recurse(3));print(pure(40));if false{unused();}}
''', {"main": 1, "keep": 1, "child": 2, "recurse": 4, "pure": 4, "identity<i64>": 4}, "11\n21\n4\n41\n"),
    ("channels", r'''
fn increment(n:i64)->i64{return n+1;}
fn producer(queue:channel<i64>)->unit !{task}{var n:i64=0;while n<3{task_yield();assert(task_send(queue,n));n=n+1;}assert(task_close(queue));}
fn consumer(queue:channel<i64>)->i64 !{task}{var n:i64=0;var total:i64=0;while n<3{total=total+increment(unwrap(task_recv(queue)));n=n+1;}return total;}
fn main()->unit !{task,io}{let result:i64=with_tasks(2,fn(scope:task_scope)->i64 !{task}{let queue:channel<i64>=channel_new<i64>(scope,0);let first:task<unit>=task_spawn(scope,fn()->unit !{task}{producer(queue);});let second:task<i64>=task_spawn(scope,fn()->i64 !{task}{return consumer(queue);});task_wait(first);return task_wait(second);});print(result);}
''', {"main": 1, "producer": 1, "consumer": 1, "increment": 3}, "6\n"),
    ("pure_descriptor", r'''
fn pure(n:i64)->i64{return n+1;}
fn callback(scope:task_scope)->i64{return pure(41);}
fn main()->unit !{task,io}{print(with_tasks(1,callback));}
''', {"main": 1, "callback": 1, "pure": 1}, "42\n"),
    ("parallel_helper", r'''
fn pure(n:i64)->i64{return n+1;}
fn item(n:i64)->i64{return pure(n);}
fn mapped()->list<i64>{return parallel_map([1,2,3],item,2);}
fn main()->unit !{task,io}{task_yield();let values:list<i64>=mapped();print(values[0]+values[1]+values[2]);}
''', {"main": 1, "mapped": 1, "item": 3, "pure": 3}, "9\n"),
    ("early_result", r'''
fn maybe(n:i64)->result<i64> !{task}{task_yield();if n==0{return err<i64>("EXPECTED","ordinary error result");}return ok(n);}
fn work()->result<i64> !{task}{let value:i64=maybe(0)?;return ok(value+1);}
fn main()->unit !{task,io}{let observed:result<i64>=work();assert(error_code(observed)=="EXPECTED");print("result retained");}
''', {"main": 1, "work": 1, "maybe": 1}, "result retained\n"),
    ("reads", r'''
server fn text(path:str)->result<str> !{task,fs}{task_yield();return file_read_text(path);}
server fn data(path:str)->result<bytes> !{task,fs}{task_yield();return file_read_bytes(path);}
server fn size(value:str)->i64{return len(value);}
server fn main()->unit !{task,fs,io}{let read:str=unwrap(text("text"));assert(size(read)==4);assert(len(unwrap(data("bytes")))==3);assert(error_code(text("missing"))=="NOT_FOUND");print(size(read));}
''', {"main": 1, "text": 2, "data": 1, "size": 2}, "4\n"),
]
FAILURE = r'''
fn leaf(n:i64)->i64{let retained:list<str>=["held","🧠"];assert(len(retained)==2);return 10/n;}
fn task_leaf()->i64 !{task}{task_yield();return leaf(0);}
fn main()->unit !{task,io}{print("before trap");print(task_leaf());}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("nex", type=Path)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    compiler = str(options.nex.resolve())
    requested = options.output or (Path(os.environ["NEX_TASK_PROFILE_OUTPUT"]) if os.environ.get("NEX_TASK_PROFILE_OUTPUT") else None)
    temporary = tempfile.TemporaryDirectory(prefix="nex task profile native ") if requested is None else None
    output = Path(temporary.name) if temporary else requested.resolve()
    if not temporary:
        output.mkdir(parents=True, exist_ok=False)
    workspace = output / "work"
    workspace.mkdir()
    (workspace / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.22", "entry": "calls.nex"}))
    grant = workspace / "grant"
    grant.mkdir()
    (grant / "text").write_bytes("A🧠\0B".encode())
    (grant / "bytes").write_bytes(b"A\0\xff")
    environment = dict(os.environ, NEX_FILES_ROOT=str(grant))
    for name in ("NEX_RESOURCE_DIR", "NEX_PROFILE_OUTPUT", "NEX_TRACY", "NEX_FILES_WRITE"):
        environment.pop(name, None)
    commands = []
    report = {"schema": "nex.task-profile-native-test/1", "ok": False, "commands": 0,
              "scenarios": [], "numerical_timing_or_speed_claim": False,
              "reference_profiling_claim": False}

    def run(*arguments, success=True, exit_code=None):
        command = [compiler, *map(str, arguments), "--json"]
        result = subprocess.run(command, cwd=workspace, env=environment, capture_output=True, text=True, timeout=300)
        commands.append(dict(command=command, cwd=str(workspace), exit=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (output / "commands.json").write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n")
        expected_exit = (0 if success else 1) if exit_code is None else exit_code
        assert result.returncode == expected_exit, commands[-1]
        return json.loads(result.stdout)

    def measured_functions(saved):
        assert saved["schema"] == "nex.profile/2", saved
        functions = {item["name"]: item for item in saved["functions"] if item["calls"]}
        assert len(functions) == sum(bool(item["calls"]) for item in saved["functions"]), saved
        for item in functions.values():
            assert item["calls"] == item["completed"] + item["aborted"], item
            assert item["node_id"] and len(item["content_hash"]) == 64, item
        return functions

    def standalone(executable, extra_environment):
        command = [str(executable)]
        result = subprocess.run(command, cwd=workspace, env={**environment, **extra_environment},
                                capture_output=True, text=True, timeout=60)
        commands.append(dict(command=command, cwd=str(workspace), environment=extra_environment,
                             exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
        (output / "commands.json").write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n")
        return result

    def profile(source, expected, stdout, success=True, error=None, events=None, multiple_resumes=True):
        arguments = ["profile", source, "--scenario", source.stem]
        if events is not None:
            arguments += ["--events", str(events)]
        session = run(*arguments, success=success, exit_code=70 if error else None)
        assert session["schema"] == "nex.profile-session/2", session
        assert session["stdout"] == stdout, session
        saved = json.loads(Path(session["output"]).read_text())
        assert saved["build"]["revision"] == session["revision"], saved
        assert saved["build"]["build_key"] == session["build_key"], saved
        assert saved["build"]["language"] == "0.22", saved
        assert saved["build"]["compiler_build"] and saved["build"]["source_hash"], saved
        for complete in ("aggregates", "memory", "cpu", "elapsed", "lifetime"):
            assert saved["completeness"][complete], (complete, saved)
        if events == 0:
            assert not saved["completeness"]["timeline"] and saved["dropped_events"] > 0, saved
        else:
            assert saved["completeness"]["timeline"], saved
        for counter in ("dropped_tasks", "dropped_invocations", "dropped_guards", "suppressed_hooks",
                        "invalid_transitions", "clock_failures", "counter_overflows",
                        "serialization_overflows", "dropped_allocations", "untracked_frees"):
            assert saved[counter] == 0, (counter, saved)
        functions = measured_functions(saved)
        for name, count in expected.items():
            item = functions[f"task_measure::{name}"]
            assert item["calls"] == count, (name, count, item)
            assert item["aborted"] == (count if error else 0), item
        assert "task_measure::unused" not in functions, functions
        assert saved["tasks"] and all(task["resumes"] >= 1 for task in saved["tasks"]), saved
        if multiple_resumes:
            assert sum(task["resumes"] for task in saved["tasks"]) > 1, saved
        for task in saved["tasks"]:
            assert task["terminal"] and task["active_invocations"] == 0, task
        invocations = {item["id"]: item for item in saved["invocations"]}
        assert len(invocations) == len(saved["invocations"]), saved
        for item in invocations.values():
            assert item["outcome"] != "active", item
            if item["parent_id"]:
                assert invocations[item["parent_id"]]["task_id"] == item["task_id"], item
        if error:
            assert session["exit_code"] == 70 and error in session["stderr"], session
        else:
            assert session["exit_code"] == 0, session
        for pool in saved["memory"]:
            assert pool["live"] == 0 and pool["live_shallow_bytes"] == 0, pool
            assert pool["allocations"] == pool["frees"], pool
        return session, saved

    try:
        descriptor = run("describe")
        report["descriptor_language"] = descriptor["version"]
        for name, body, expected, stdout in SCENARIOS:
            source = workspace / (name + ".nex")
            source.write_text("module task_measure;\n" + body)
            reference = run("eval", source)
            native = run("run", source, "--profile", "release")
            assert reference["stdout"] == native["stdout"] == stdout, (name, reference, native)
            session, saved = profile(source, expected, stdout, multiple_resumes=name != "pure_descriptor")
            built = run("build", source, "--profile", "profile")
            metadata = json.loads((Path(built["executable"]).parent / "build.json").read_text())
            assert metadata["runtime_requirements"]["tasks"] and metadata["runtime_requirements"]["profiling"], metadata
            for resource in ("nex_task_profile_site.h", "nex_task_profile.h", "nex_task_profile.cpp"):
                assert resource in metadata["runtime_inputs"], metadata
            assert metadata["runtime_components"].count("nex_task_profile.cpp") == 1, metadata
            llvm = Path(built["llvm"]).read_text()
            assert "nex_task_profile_prepare" in llvm and "__task_step" in llvm, llvm
            if name == "calls":
                dormant = standalone(built["executable"], {})
                assert dormant.returncode == 0 and dormant.stdout == stdout and not dormant.stderr, dormant
                rejected_path = output / "task-tracy-must-not-start.json"
                rejected = standalone(built["executable"], {"NEX_TRACY": "1", "NEX_PROFILE_OUTPUT": str(rejected_path)})
                assert rejected.returncode == 70 and rejected.stdout == "" and "E_TASK_PROFILE" in rejected.stderr, rejected
                assert not rejected_path.exists(), rejected_path
                report["profile_dormant_agreement"] = True
                report["task_tracy_rejected_before_source_output"] = True
                _, capped = profile(source, expected, stdout, events=0)
                assert measured_functions(capped).keys() == measured_functions(saved).keys()
            report["scenarios"].append(name)
        source = workspace / "failure.nex"
        source.write_text("module task_measure;\n" + FAILURE)
        reference = run("eval", source, success=False)
        native = run("run", source, "--profile", "release", success=False, exit_code=70)
        assert reference["code"] == "E_DIV_ZERO" and "E_DIV_ZERO" in json.dumps(native), (reference, native)
        assert reference["stdout"] == native["stdout"] == "before trap\n", (reference, native)
        profile(source, {"main": 1, "task_leaf": 1, "leaf": 1}, "before trap\n", success=False, error="E_DIV_ZERO")
        report["scenarios"].append("failure")
        report["ok"] = True
    finally:
        report["commands"] = len(commands)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
