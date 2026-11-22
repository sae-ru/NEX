"""Create a clean project and verify submitted source against the shared invoice oracle."""
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

import cpp_fixture
import fixture as shared
import python_fixture


PORTS = {"cpp": cpp_fixture, "python": python_fixture}
POLICY = shared.POLICY.split("\nRun ./nex", 1)[0] + "\nRun ./test from the project root for the disputed invoice. Adjust application code only.\n"


def sources(language):
    return shared.SOURCES if language == "nex" else PORTS[language].SOURCES


def _entry(language, hidden):
    if language == "nex":
        return "hidden.nex" if hidden else shared.PROJECT_ENTRY
    return PORTS[language].HIDDEN_ENTRY if hidden else PORTS[language].VISIBLE_ENTRY


def _driver(language, hidden):
    if language == "nex":
        return shared.held_out() if hidden else shared.visible()
    generator = PORTS[language].held_out if hidden else PORTS[language].visible
    return generator(shared)


def _launcher(language, executable, entry):
    tool = Path(executable)
    if not tool.is_absolute() or not tool.is_file():
        raise ValueError(f"expected an absolute path to {language} tool")
    # Preserve the name clang++: the driver uses argv[0] to select the C++ linker.
    quoted = shlex.quote(str(tool))
    start = '#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\n'
    if language == "nex":
        return start + f"exec {quoted} test {shlex.quote(entry)} --json\n"
    if language == "python":
        return start + f"exec {quoted} -E -B {shlex.quote(entry)}\n"
    if language == "cpp":
        # Codex starts its tools without the parent's SDKROOT. The raw Apple compiler
        # needs an explicit sysroot to find the C++ standard library in that environment.
        sdk = ' -isysroot "$(xcrun --sdk macosx --show-sdk-path)"' if sys.platform == "darwin" else ""
        return (start + 'out=$(mktemp -d)\n' + """trap 'rm -rf "$out"' EXIT\n""" +
                f'{quoted}{sdk} -std=c++20 -O0 {shlex.quote(entry)} -o "$out/invoice-test"\n' +
                '"$out/invoice-test"\n')
    raise ValueError(f"unrecognized language {language}")


def public_files(language, executable):
    name = _entry(language, False)
    data = {"README.md": POLICY, name: _driver(language, False),
            "test": _launcher(language, executable, name)}
    if language == "nex":
        data["nex.json"] = shared.PROTECTED["nex.json"]
    return data


def create(root, language, executable):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, value in {**sources(language), **public_files(language, executable)}.items():
        with (root / name).open("x", encoding="utf-8") as f:
            f.write(value)
    (root / "test").chmod(0o755)


def _execute(root, script):
    proc = subprocess.run([str(root / script)], cwd=root, capture_output=True, timeout=90)
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", errors="replace")


def reproduction(root, language, executable):
    root = Path(root).resolve(strict=True)
    if (root / "test").read_text() != public_files(language, executable)["test"]:
        return False
    try:
        code, output = _execute(root, "test")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return (code != 0 and re.search(r"\b1252\b", output) is not None and
            re.search(r"\b2079\b", output) is not None)


def _check(root, language, executable, hidden):
    entry = _entry(language, hidden)
    if language == "nex":
        symbol = ("warehouse::acceptance::hidden_billing_contract" if hidden else
                  "warehouse::billing_test::disputed_storage_invoice")
        return shared.check(executable, root, entry, symbol)
    script = "test"
    if hidden:
        script = "run-hidden"
        (root / script).write_text(_launcher(language, executable, entry), encoding="utf-8")
        (root / script).chmod(0o755)
    try:
        code, _ = _execute(root, script)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "TIMEOUT"}
    except OSError:
        return {"ok": False, "code": "EXEC_FAILED"}
    return {"ok": code == 0, "exit": code}


def verify(root, language, executable):
    root = Path(root)
    with tempfile.TemporaryDirectory(prefix="depot-external-check-") as folder:
        clean = Path(folder)
        create(clean, language, executable)
        for name in public_files(language, executable):
            original, submitted = clean / name, root / name
            if (submitted.is_symlink() or not submitted.is_file() or
                    submitted.stat().st_size != original.stat().st_size or
                    submitted.read_bytes() != original.read_bytes()):
                return {"ok": False, "reason": "protected input changed", "file": name}
        changed = []
        for name in sources(language):
            submitted = root / name
            if submitted.is_symlink() or not submitted.is_file() or submitted.stat().st_size > 65536:
                return {"ok": False, "reason": "invalid source", "file": name}
            data = submitted.read_bytes()
            if data != (clean / name).read_bytes():
                changed.append(name)
            (clean / name).write_bytes(data)
        (clean / _entry(language, True)).write_text(_driver(language, True), encoding="utf-8")
        checks = {key: _check(clean, language, executable, hidden)
                  for key, hidden in (("visible", False), ("hidden", True))}
        return {"ok": all(item["ok"] for item in checks.values()), "checks": checks,
                "changed_modules": changed, "held_out_cases": len(shared.CASES)-1}
