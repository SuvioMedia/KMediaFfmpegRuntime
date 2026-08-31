#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Fetch the closed native source inventory for reuse inside one workflow run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native import build  # noqa: E402


def fetch_sources(output: Path) -> None:
    if output.exists():
        raise ValueError("source output directory already exists")
    output.mkdir(parents=True)

    for component in build.COMPONENTS:
        manifest = build.load_json(ROOT / f"compliance/components/{component}.json")
        destination = output / manifest["sourceArchive"]
        build.download(manifest["sourceUrl"], destination)
        if build.sha256(destination) != manifest["sourceSha256"]:
            raise ValueError(f"{component} source SHA-256 differs from policy")

    ffmpeg = build.load_json(ROOT / "compliance/components/ffmpeg.json")
    build.download(ffmpeg["signatureUrl"], output / (ffmpeg["sourceArchive"] + ".asc"))
    build.download("https://ffmpeg.org/ffmpeg-devel.asc", output / "ffmpeg-devel.asc")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    fetch_sources(arguments.output.resolve())
    print(f"fetched {len(build.COMPONENTS)} hash-bound native source archives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
