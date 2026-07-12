#!/usr/bin/env python3
"""Resolve exact packaged SDK metadata for one immutable BSR module commit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


REMOTE = re.compile(
    r"^\s*-\s+remote:\s+"
    r"(buf\.build/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):"
    r"(v[0-9]+(?:\.[0-9]+){1,2})\s*$"
)
REVISION = re.compile(r"^\s+revision:\s+([1-9][0-9]*)\s*$")


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
    pins: list[tuple[str, str, int]] = []
    pending: tuple[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        remote = REMOTE.fullmatch(line)
        if remote:
            if pending is not None:
                raise SystemExit(f"generator {pending[0]} is missing a revision")
            pending = (remote.group(1), remote.group(2))
            continue
        revision = REVISION.fullmatch(line)
        if revision and pending is not None:
            pins.append((*pending, int(revision.group(1))))
            pending = None
    if pending is not None:
        raise SystemExit(f"generator {pending[0]} is missing a revision")
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
