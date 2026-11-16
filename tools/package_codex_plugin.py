#!/usr/bin/env python3
"""Validate and reproducibly package the public NEX skill/plugin (stdlib only)."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "nex"
FILES = (
    "LICENSE", "PUBLISHING.md", "README.md", "README.ru.md",
    "assets/icon-dark.svg", "assets/icon.svg", "plugin.json",
    "skills/nex-programming/LICENSE",
    "skills/nex-programming/SKILL.md",
    "skills/nex-programming/agents/openai.yaml",
    "skills/nex-programming/assets/hello.nex",
    "skills/nex-programming/references/sdk-setup.md",
    "skills/nex-programming/references/workflows.md",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate():
    require(PLUGIN.is_dir() and not PLUGIN.is_symlink(), "Missing plugin directory")
    actual = set()
    for path in PLUGIN.rglob("*"):
        require(not path.is_symlink(), "Symlink in plugin: " + str(path))
        if path.is_file():
            actual.add(path.relative_to(PLUGIN).as_posix())
    require(actual == set(FILES), "Plugin inventory differs: " + repr(actual ^ set(FILES)))
    contents = {name: (PLUGIN / name).read_bytes() for name in FILES}
    for data in contents.values():
        data.decode("utf-8", errors="strict")
    manifest = json.loads(contents["plugin.json"])
    require(manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "Unexpected manifest schema")
    require(manifest["name"] == "nex-developer-tools", "Unexpected plugin name")
    require(re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]), "Use a release version")
    require(manifest["license"] == "MIT", "Unexpected license")
    require(contents["LICENSE"] == (ROOT / "LICENSE").read_bytes(), "Plugin license differs")
    require(contents["skills/nex-programming/LICENSE"] == contents["LICENSE"],
            "Standalone skill license differs")
    extension = manifest["extensions"]["com.openai"]
    require(extension["requires_local_executor"] is True, "Local executor must be declared")
    require(not {"apps", "hooks", "mcpServers"} & extension.keys(), "Expected skills-only package")
    interface = extension["interface"]
    for field, limit in (("displayName", 30), ("shortDescription", 30),
                         ("longDescription", 4000), ("developerName", 80)):
        require(isinstance(interface[field], str) and 0 < len(interface[field]) <= limit,
                "Invalid listing field: " + field)
    for field in ("composerIcon", "composerIconDark", "logo", "logoDark"):
        relative = interface[field]
        require(relative.startswith("./") and relative[2:] in contents, "Missing icon: " + field)
        svg = ET.fromstring(contents[relative[2:]])
        width, height = int(svg.attrib["width"]), int(svg.attrib["height"])
        require(width == height and 48 <= width <= 4096, "Invalid square icon dimensions")
    require(len(interface["defaultPrompt"]) <= 3, "Too many starter prompts")
    require(all(0 < len(value) <= 128 for value in interface["defaultPrompt"]),
            "Invalid starter prompt")
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    entries = [entry for entry in marketplace["plugins"] if entry["name"] == manifest["name"]]
    require(len(entries) == 1, "Missing unique marketplace entry")
    require(entries[0]["source"] == {"source": "local", "path": "./plugins/nex"},
            "Marketplace points to a different package")
    return manifest, contents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Artifact directory outside plugin")
    args = parser.parse_args()
    manifest, contents = validate()
    destination = args.output.resolve()
    require(destination != PLUGIN and PLUGIN not in destination.parents,
            "Output must be outside the packaged plugin")
    destination.mkdir(parents=True, exist_ok=True)
    stem = manifest["name"] + "-" + manifest["version"]
    archive = destination / (stem + ".zip")
    # Fixed timestamp, permissions, ordering and storage avoid platform/zlib variance.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for name in sorted(contents):
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, contents[name])
    with zipfile.ZipFile(archive) as bundle:
        require(bundle.testzip() is None, "Damaged ZIP")
        require(set(bundle.namelist()) == set(FILES), "ZIP inventory differs")
        require(all(bundle.read(name) == data for name, data in contents.items()), "ZIP data differs")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    inventory = {
        "schema": "nex.codex-plugin-package/1", "name": manifest["name"],
        "version": manifest["version"], "archive": archive.name,
        "bytes": archive.stat().st_size, "sha256": digest,
        "files": [{"path": name, "bytes": len(contents[name]),
                   "sha256": hashlib.sha256(contents[name]).hexdigest()} for name in sorted(contents)],
        "directory_submitted": False, "directory_approved": False,
    }
    (destination / (stem + ".inventory.json")).write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / (stem + ".sha256")).write_text(digest + "  " + archive.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(archive), "files": len(contents),
                      "bytes": inventory["bytes"], "sha256": digest}))


if __name__ == "__main__":
    main()
