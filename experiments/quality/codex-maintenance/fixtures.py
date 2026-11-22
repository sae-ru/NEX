"""Small NEX 0.30 application maintenance tasks and an out-of-process acceptance oracle.

Only create() output belongs in a model's working directory. verify() imports
allowed source files into a fresh project, then runs trusted visible and
held-out checks. The control solutions below are for preflight use only.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


TASKS = {
    "summary-repair": (
        "The workboard dashboard occasionally reports an incorrect character total. "
        "Repair summarize in model.nex. It must report the item count, completed count "
        "and total length of all item texts in Unicode scalars. Preserve its public "
        "interface. Edit only model.nex. Run the visible tests."
    ),
    "retry-delay": (
        "Implement the TODO retry_seconds(attempt: i64) -> i64 in policy.nex. "
        "Our scheduler returns zero seconds for a negative attempt, one second for "
        "attempt zero and doubles the delay for each additional attempt up to a ceiling "
        "of 30 seconds. The full i64 input range must terminate quickly without "
        "overflow. Edit only policy.nex. Run the visible tests."
    ),
    "queue-interface": (
        "The dashboard now needs both pending and total counts. In queue.nex add "
        "a public record Counts with fields pending and total (both i64, in that "
        "order) and a public counts(jobs: list<bool>) -> Counts. In this list true "
        "means completed. Keep pending_count for older callers. Update "
        "render(jobs) in dashboard.nex to consume counts and return the exact text "
        "'P/T pending' using decimal counts. Edit only queue.nex and dashboard.nex. "
        "Run the visible tests."
    ),
}

_SOURCES = {
    "summary-repair": {"model.nex": """module board::model;
pub struct Item { text: str; done: bool; }
pub struct Summary { total: i64; done: i64; characters: i64; }

pub fn summarize(items: list<Item>) -> Summary {
  var characters: i64 = 0;
  var done: i64 = 0;
  var index: i64 = 0;
  while index < len(items) {
    characters = len(items[index].text);
    if items[index].done { done = done + 1; }
    index = index + 1;
  }
  return Summary(len(items), done, characters);
}
"""},
    "retry-delay": {"policy.nex": """module jobs::policy;
pub fn retry_seconds(attempt: i64) -> i64 {
  // TODO: implement the scheduler policy.
  return 0;
}
"""},
    "queue-interface": {
        "queue.nex": """module board::queue;
pub fn pending_count(jobs: list<bool>) -> i64 {
  var remaining: i64 = 0;
  var index: i64 = 0;
  while index < len(jobs) {
    if !jobs[index] { remaining = remaining + 1; }
    index = index + 1;
  }
  return remaining;
}
""",
        "dashboard.nex": """module board::dashboard;
import "./queue.nex" as queue;
pub fn render(jobs: list<bool>) -> str {
  return str(queue::pending_count(jobs)) + " pending";
}
""",
    },
}

_IMPORTS = {
    "summary-repair": 'import "./model.nex" as model;',
    "retry-delay": 'import "./policy.nex" as policy;',
    "queue-interface": 'import "./dashboard.nex" as dashboard;\nimport "./queue.nex" as queue;',
}
_VISIBLE = {
    "summary-repair": [
        'assert(model::summarize([model::Item("desk", true), model::Item("cat", false)]) == model::Summary(2, 1, 7));'
    ],
    "retry-delay": [
        "assert(policy::retry_seconds(0) == 1);",
        "assert(policy::retry_seconds(2) == 4);",
    ],
    "queue-interface": [
        'assert(dashboard::render([true, false]) == "1/2 pending");',
        "assert(queue::pending_count([false]) == 1);",
    ],
}


def _assertions(task):
    if task == "summary-repair":
        inputs = [
            [], [("😺", False)], [("é", True), ("e\u0301", True), ("", False)],
            [("汉🙂", False), ("ab", True), ("🧠xy", False), ("", False)],
        ]
        result = []
        for items in inputs:
            values = ", ".join(
                "model::Item(" + json.dumps(text, ensure_ascii=False) + ", " + str(done).lower() + ")"
                for text, done in items)
            counts = len(items), sum(done for _, done in items), sum(len(text) for text, _ in items)
            result.append(f"assert(model::summarize([{values}]) == model::Summary({counts[0]}, {counts[1]}, {counts[2]}));")
        return result
    if task == "retry-delay":
        attempts = ["(-9223372036854775807 - 1)", "-6", "-1", "0", "1", "2", "3",
                    "4", "5", "6", "30", "63", "9223372036854775807"]
        expected = [0, 0, 0, 1, 2, 4, 8, 16, 30, 30, 30, 30, 30]
        return [f"assert(policy::retry_seconds({a}) == {n});" for a, n in zip(attempts, expected)]
    result = []
    for index, jobs in enumerate(([], [True], [False, False], [True, False, True, False, False])):
        values = "[" + ", ".join(str(v).lower() for v in jobs) + "]"
        pending = jobs.count(False)
        result.extend((
            f"let item{index}: queue::Counts = queue::counts({values});",
            f"assert(item{index}.pending == {pending} && item{index}.total == {len(jobs)});",
            f"assert(item{index} == queue::Counts({pending}, {len(jobs)}));",
            f"assert(queue::pending_count({values}) == {pending});",
            f'assert(dashboard::render({values}) == "{pending}/{len(jobs)} pending");',
        ))
    return result


def _driver(task, name, statements):
    body = "\n".join("  " + statement for statement in statements)
    return (f"module trial::{name};\n{_IMPORTS[task]}\n\nfn main() -> unit {{}}\n"
            f"test fn {name}_contract() -> unit {{\n{body}\n}}\n")


def create(task, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    files = {
        **_SOURCES[task],
        "visible.nex": _driver(task, "visible", _VISIBLE[task]),
        "nex.json": '{"schema":"nex.project/1","language":"0.30","entry":"visible.nex"}\n',
    }
    for name, source in files.items():
        with (root / name).open("x", encoding="utf-8") as file:
            file.write(source)


def _test(nex, project, name):
    command = [nex, "test", name + ".nex", "--json"]
    try:
        result = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return {"ok": False, "reason": "invalid compiler response", "exit": result.returncode}
    tests = payload.get("tests", [])
    native = any(row.get("name", "").endswith(name + "_contract") and
                 row.get("ok") is True and row.get("native") is True for row in tests)
    return {"ok": result.returncode == 0 and payload.get("ok") is True and native,
            "exit": result.returncode, "code": payload.get("code"), "native": native}


def verify(task, directory, nex):
    root = Path(directory)
    compiler = str(Path(nex).resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix="nex-accept-") as folder:
        clean = Path(folder)
        create(task, clean)
        for name in ("nex.json", "visible.nex"):
            path = root / name
            if path.is_symlink() or not path.is_file() or path.read_bytes() != (clean / name).read_bytes():
                return {"ok": False, "reason": "protected input changed", "file": name}
        # Ignore the model's SDK caches and other incidental files; only allowlisted
        # application sources can enter the freshly constructed acceptance project.
        hashes = {}
        for name in _SOURCES[task]:
            path = root / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 32000:
                return {"ok": False, "reason": "missing or invalid source", "file": name}
            source = path.read_bytes()
            (clean / name).write_bytes(source)
            hashes[name] = hashlib.sha256(source).hexdigest()
        (clean / "held_out.nex").write_text(_driver(task, "held_out", _assertions(task)), encoding="utf-8")
        checks = {name: _test(compiler, clean, name) for name in ("visible", "held_out")}
        if task == "queue-interface":
            # Prove the display consumes the new API, even when reimplementing
            # its logic locally would have produced identical visible results.
            (clean / "queue.nex").write_text(
                "module board::queue;\npub struct Counts { pending: i64; total: i64; }\n"
                "pub fn pending_count(jobs: list<bool>) -> i64 { return 0; }\n"
                "pub fn counts(jobs: list<bool>) -> Counts { return Counts(17, 23); }\n",
                encoding="utf-8")
            (clean / "consumer.nex").write_text(
                _driver(task, "consumer", ['assert(dashboard::render([]) == "17/23 pending");']),
                encoding="utf-8")
            checks["consumer"] = _test(compiler, clean, "consumer")
        return {"ok": all(check["ok"] for check in checks.values()), "checks": checks, "sha256": hashes}


def preflight(nex):
    """Negative starting code and independently written positive controls for each task."""
    controls = {
        "summary-repair": {"model.nex": _SOURCES["summary-repair"]["model.nex"].replace(
            "characters = len(", "characters = characters + len(")},
        "retry-delay": {"policy.nex": """module jobs::policy;
pub fn retry_seconds(attempt: i64) -> i64 {
  if attempt < 0 { return 0; }
  if attempt >= 5 { return 30; }
  var delay: i64 = 1; var i: i64 = 0;
  while i < attempt { delay = delay * 2; i = i + 1; }
  return delay;
}
"""},
        "queue-interface": {
            "queue.nex": _SOURCES["queue-interface"]["queue.nex"] + """
pub struct Counts { pending: i64; total: i64; }
pub fn counts(jobs: list<bool>) -> Counts { return Counts(pending_count(jobs), len(jobs)); }
""",
            "dashboard.nex": _SOURCES["queue-interface"]["dashboard.nex"].replace(
                'return str(queue::pending_count(jobs)) + " pending";',
                'let value: queue::Counts = queue::counts(jobs);\n  return str(value.pending) + "/" + str(value.total) + " pending";'),
        },
    }
    report = {}
    for task in TASKS:
        with tempfile.TemporaryDirectory(prefix="nex-control-") as folder:
            project = Path(folder)
            create(task, project)
            bad = verify(task, project, nex)
            for name, source in controls[task].items():
                (project / name).write_text(source, encoding="utf-8")
            good = verify(task, project, nex)
            meaningful_failure = all(not check["ok"] and check.get("exit", 0) != 0 and check.get("code")
                                     for check in bad.get("checks", {}).values()) and bool(bad.get("checks"))
            report[task] = {"ok": bool(meaningful_failure and good["ok"]), "starter": bad, "control": good}
    return {"ok": all(item["ok"] for item in report.values()), "tasks": report}
