#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    components = []
    for path in sorted(args.components.glob("*.json")):
        value = json.loads(path.read_text())
        components.append({
            "type": "library", "name": value["name"], "version": value["version"],
            "licenses": [{"license": {"id": value["builtOutputLicenseSpdx"]}}],
            "externalReferences": [{"type": "distribution", "url": value["sourceUrl"]}],
            "hashes": [{"alg": "SHA-256", "content": value["sourceSha256"]}],
        })
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {"component": {"type": "library", "name": "KMediaFfmpegRuntime", "version": args.version}},
        "components": components,
    }
    args.output.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
