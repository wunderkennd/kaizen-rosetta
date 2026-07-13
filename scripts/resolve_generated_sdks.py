#!/usr/bin/env python3
"""Resolve exact packaged SDK metadata for one immutable BSR module commit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


PLUGIN_ITEM = re.compile(
    r"^  -(?:\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.*))?$"
)
PLUGIN_FIELD = re.compile(r"^    ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
REMOTE = re.compile(
    r"(buf\.build/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):"
    r"(v[0-9]+(?:\.[0-9]+){1,2})"
)
REVISION = re.compile(r"[1-9][0-9]*")


def coordinate(generator: str) -> tuple[str, str]:
    owner, plugin = generator.removeprefix("buf.build/").split("/")
    if plugin == "go":
        return "go", f"buf.build/gen/go/kaizen/rosetta/{owner}/{plugin}"
    if plugin in {"es"}:
        return "npm", f"@buf/kaizen_rosetta.{owner}_{plugin}"
    if plugin in {"python", "pyi", "py"}:
        return "python", f"kaizen-rosetta-{owner}-{plugin}"
    raise SystemExit(f"no packaged SDK coordinate mapping for {generator}")


def parse_pins(path: Path) -> list[tuple[str, str, int]]:
    plugin_entries: list[dict[str, str]] = []
    current_entry: dict[str, str] | None = None
    in_plugins = False

    for line in path.read_text(encoding="utf-8").splitlines():
        if not in_plugins:
            if re.fullmatch(r"plugins:\s*(?:#.*)?", line):
                in_plugins = True
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break

        item = PLUGIN_ITEM.fullmatch(line)
        if item:
            if current_entry is not None:
                plugin_entries.append(current_entry)
            current_entry = {}
            if item.group(1) is not None:
                current_entry[item.group(1)] = item.group(2).strip()
            continue

        field = PLUGIN_FIELD.fullmatch(line)
        if field and current_entry is not None:
            current_entry[field.group(1)] = field.group(2).strip()

    if current_entry is not None:
        plugin_entries.append(current_entry)

    pins: list[tuple[str, str, int]] = []
    for entry in plugin_entries:
        remote_text = entry.get("remote")
        if remote_text is None:
            continue
        remote = REMOTE.fullmatch(remote_text)
        if remote is None:
            continue
        revision_text = entry.get("revision")
        if revision_text is None or REVISION.fullmatch(revision_text) is None:
            raise SystemExit(f"generator {remote.group(1)} is missing a revision")
        pins.append((remote.group(1), remote.group(2), int(revision_text)))
    if not pins:
        raise SystemExit("no pinned remote generators found")
    return pins


def resolve(
    buf_bin: str,
    module: str,
    commit: str,
    generator: str,
    plugin_version: str,
    plugin_revision: int,
) -> dict[str, Any]:
    ecosystem, package_coordinate = coordinate(generator)
    result = subprocess.run(
        [
            buf_bin,
            "registry",
            "sdk",
            "info",
            "--module",
            f"{module}:{commit}",
            "--plugin",
            f"{generator}:{plugin_version}",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        lower_error = result.stderr.lower()
        if any(token in lower_error for token in ("not_found", "not found", "unavailable")):
            return {
                "ecosystem": ecosystem,
                "generator": generator,
                "moduleCommit": commit,
                "pluginRevision": plugin_revision,
                "pluginVersion": plugin_version,
                "reason": "BSR reports no packaged generated SDK for this plugin",
                "publicationStatus": "unavailable",
            }
        raise SystemExit(
            f"failed to resolve generated SDK for {generator}: "
            f"{result.stderr.strip()}"
        )
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"generated SDK lookup for {generator} returned invalid JSON: {error}"
        ) from error
    module_info = info.get("module", {})
    plugin_info = info.get("plugin", {})
    expected_owner, expected_name = generator.removeprefix("buf.build/").split("/")
    if module_info.get("commit") != commit:
        raise SystemExit(f"generated SDK module commit mismatch for {generator}")
    if (
        plugin_info.get("owner") != expected_owner
        or plugin_info.get("name") != expected_name
        or plugin_info.get("version") != plugin_version
        or plugin_info.get("revision") != plugin_revision
    ):
        raise SystemExit(f"generated SDK plugin pin mismatch for {generator}")
    sdk_version = info.get("version")
    if not isinstance(sdk_version, str) or not sdk_version:
        raise SystemExit(f"generated SDK version missing for {generator}")
    if commit[:12] not in sdk_version:
        raise SystemExit(f"generated SDK version/commit association mismatch for {generator}")
    return {
        "coordinate": package_coordinate,
        "ecosystem": ecosystem,
        "generator": generator,
        "moduleCommit": commit,
        "pluginRevision": plugin_revision,
        "pluginVersion": plugin_version,
        "publicationStatus": "published",
        "version": sdk_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--buf", default="buf")
    parser.add_argument("--buf-gen", type=Path, required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    sdks = [
        resolve(
            arguments.buf,
            arguments.module,
            arguments.commit,
            generator,
            version,
            revision,
        )
        for generator, version, revision in parse_pins(arguments.buf_gen)
    ]
    document = {
        "moduleCommit": arguments.commit,
        "sdks": sorted(sdks, key=lambda sdk: sdk["generator"]),
    }
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
