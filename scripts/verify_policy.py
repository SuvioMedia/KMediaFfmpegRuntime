#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    policy = load(root / "compliance/policy/release-policy.json")
    component_dir = root / "compliance/components"
    expected = set(policy["components"])
    actual = {path.stem for path in component_dir.glob("*.json")}
    if actual != expected:
        raise ValueError(f"component inventory differs: expected {sorted(expected)}, got {sorted(actual)}")

    ffmpeg = load(component_dir / "ffmpeg.json")
    arguments = set(ffmpeg["buildArguments"])
    missing = set(policy["requiredFfmpegArguments"]) - arguments
    forbidden = set(policy["forbiddenFfmpegArguments"]) & arguments
    if missing or forbidden:
        raise ValueError(f"FFmpeg policy mismatch; missing={sorted(missing)}, forbidden={sorted(forbidden)}")
    if ffmpeg["linkage"] != "dynamic" or ffmpeg["builtOutputLicenseSpdx"] != "LGPL-2.1-or-later":
        raise ValueError("FFmpeg output must be dynamic LGPL-2.1-or-later")
    if ffmpeg["libraries"] != ["avcodec", "avfilter", "avformat", "avutil", "swresample", "swscale"]:
        raise ValueError("FFmpeg shared-library inventory is not closed")

    targets = policy["targets"]
    if set(targets) & set(policy["forbiddenTargets"]):
        raise ValueError("a forbidden architecture is release eligible")
    required_targets = {
        "android-arm64-v8a", "android-armeabi-v7a", "linux-x86_64", "linux-aarch64",
        "windows-x86_64", "macos-aarch64", "ios-arm64", "ios-simulator-arm64",
    }
    if set(targets) != required_targets:
        raise ValueError("target matrix differs from the public contract")

    loader_roots = [
        root / "runtime-shared/src/main/java",
        root / "runtime-ffmpeg-shared/src/main/java",
        root / "ass-runtime-desktop/src/main/java",
        root / "runtime-desktop/src/main/java",
        root / "ass-runtime-android/src/main/java",
        root / "runtime-android/src/main/java",
    ]
    loader_sources = sorted(path for directory in loader_roots for path in directory.rglob("*.java"))
    if not loader_sources:
        raise ValueError("project-authored Java loader inventory is empty")
    expected_loader_spdx = "// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later"
    invalid_loader_licenses = [
        path.relative_to(root)
        for path in loader_sources
        if path.read_text(encoding="utf-8").splitlines()[0] != expected_loader_spdx
    ]
    if invalid_loader_licenses:
        raise ValueError(
            "Java loader sources must remain dual-licensed for Native Image consumers: "
            f"{invalid_loader_licenses}"
        )

    required_legal_files = [
        root / "LICENSE",
        root / "LICENSES/MIT.txt",
        root / "LICENSES/LGPL-2.1.txt",
        root / "NOTICE",
        root / "THIRD_PARTY_NOTICES.md",
        root / "docs/LICENSING.md",
        root / "docs/RELINKING.md",
    ]
    missing_legal_files = [path.relative_to(root) for path in required_legal_files if not path.is_file()]
    if missing_legal_files:
        raise ValueError(f"legal inventory is incomplete: {missing_legal_files}")
    license_map = (root / "LICENSE").read_text(encoding="utf-8")
    if "0.1.0-rc.7" not in license_map or "MIT OR LGPL-2.1-or-later" not in license_map:
        raise ValueError("root license map must preserve the explicit Native Image loader grant")

    excluded_directories = {".git", ".gradle", "build"}
    for directory, directory_names, file_names in os.walk(root):
        directory_names[:] = [name for name in directory_names if name not in excluded_directories]
        for file_name in file_names:
            path = Path(directory, file_name)
            if path.suffix in {".jar", ".zip"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if path.name not in {"release-policy.json", "verify_policy.py"}:
                lowered = text.lower()
                for token in ("android-x86_64", "macos-x86_64", "ios-simulator-x86_64"):
                    if token in lowered:
                        raise ValueError(f"forbidden target token {token!r} found in {path.relative_to(root)}")

    print("KMediaFfmpegRuntime policy verified")


if __name__ == "__main__":
    main()
