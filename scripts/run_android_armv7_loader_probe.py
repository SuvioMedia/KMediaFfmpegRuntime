#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Execute the shared native graph in a real ARMv7 Android process.

This is a loader/ABI RC gate. It deliberately records when an older official
ARMv7 image needs the two libc symbols introduced at API 28; it is not a
replacement for the stable-release framework and MediaCodec device matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/data/local/tmp/kmedia-armv7-probe"
RUNTIME_LIBRARIES = {
    "libkmediaffmpeg_ass.so",
    "libkmediaffmpeg_avcodec.so",
    "libkmediaffmpeg_avfilter.so",
    "libkmediaffmpeg_avformat.so",
    "libkmediaffmpeg_avutil.so",
    "libkmediaffmpeg_freetype.so",
    "libkmediaffmpeg_fribidi.so",
    "libkmediaffmpeg_harfbuzz.so",
    "libkmediaffmpeg_probe.so",
    "libkmediaffmpeg_swresample.so",
    "libkmediaffmpeg_swscale.so",
}
MPV_LIBRARIES = {
    "libkmediampv_jni.so",
    "libkmediampv_mpv.so",
    "libkmediampv_placebo.so",
}
BRIDGE_LIBRARIES = {"libkmediabridge.so"}


def run(*command: str, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def exact_libraries(directory: Path, expected: set[str]) -> list[Path]:
    paths = sorted(directory.glob("*.so"))
    actual = {path.name for path in paths}
    if actual != expected:
        raise ValueError(
            f"native input differs from the closed graph: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return paths


def property_value(adb: str, serial: str, name: str) -> str:
    return run(adb, "-s", serial, "shell", "getprop", name, capture=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--mpv", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    runtime = exact_libraries(arguments.runtime, RUNTIME_LIBRARIES)
    mpv = exact_libraries(arguments.mpv, MPV_LIBRARIES)
    bridge = exact_libraries(arguments.bridge, BRIDGE_LIBRARIES)
    libraries = runtime + mpv + bridge

    abi = property_value(arguments.adb, arguments.serial, "ro.product.cpu.abi")
    abi_list = property_value(arguments.adb, arguments.serial, "ro.product.cpu.abilist")
    sdk_text = property_value(arguments.adb, arguments.serial, "ro.build.version.sdk")
    kernel = run(arguments.adb, "-s", arguments.serial, "shell", "uname", "-m", capture=True)
    if abi != "armeabi-v7a" or "x86" in abi_list or kernel not in {"armv7l", "armv8l"}:
        raise ValueError(f"device is not a pure ARMv7 process target: {abi=}, {abi_list=}, {kernel=}")
    sdk = int(sdk_text)

    prebuilt_roots = sorted(
        path for path in (arguments.ndk / "toolchains/llvm/prebuilt").iterdir() if path.is_dir()
    )
    if len(prebuilt_roots) != 1:
        raise ValueError("NDK must contain exactly one host prebuilt toolchain")
    binaries = prebuilt_roots[0] / "bin"
    compiler23 = binaries / "armv7a-linux-androideabi23-clang"
    compiler28 = binaries / "armv7a-linux-androideabi28-clang"
    for compiler in (compiler23, compiler28):
        if not compiler.is_file():
            raise ValueError(f"missing NDK compiler: {compiler.name}")

    with tempfile.TemporaryDirectory(prefix="kmedia-armv7-probe-") as temporary_value:
        temporary = Path(temporary_value)
        executable = temporary / "loader-probe"
        shim = temporary / "libkmedia_api28_compat.so"
        run(
            str(compiler23),
            str(ROOT / "native/tests/android_arm_loader_probe.c"),
            "-fPIE", "-pie", "-ldl", "-o", str(executable),
        )
        compatibility_symbols: list[str] = []
        if sdk < 28:
            run(
                str(compiler28),
                str(ROOT / "native/tests/android_api28_compat.c"),
                "-shared", "-fPIC", "-Wl,-soname,libkmedia_api28_compat.so",
                "-o", str(shim),
            )
            compatibility_symbols = ["glob", "globfree"]

        run(arguments.adb, "-s", arguments.serial, "shell", "rm", "-rf", REMOTE)
        run(arguments.adb, "-s", arguments.serial, "shell", "mkdir", "-p", REMOTE)
        for path in libraries:
            run(arguments.adb, "-s", arguments.serial, "push", str(path), f"{REMOTE}/{path.name}")
        run(arguments.adb, "-s", arguments.serial, "push", str(executable), f"{REMOTE}/loader-probe")
        if compatibility_symbols:
            run(arguments.adb, "-s", arguments.serial, "push", str(shim), f"{REMOTE}/{shim.name}")
        run(arguments.adb, "-s", arguments.serial, "shell", "chmod", "700", f"{REMOTE}/loader-probe")

        environment = "LD_LIBRARY_PATH=."
        if compatibility_symbols:
            environment += " LD_PRELOAD=./libkmedia_api28_compat.so"
        probe_text = run(
            arguments.adb,
            "-s",
            arguments.serial,
            "shell",
            f"cd {REMOTE} && {environment} ./loader-probe",
            capture=True,
        )
        probe = json.loads(probe_text.splitlines()[-1])

    report = {
        "schemaVersion": 1,
        "test": "android-armv7-native-shared-loader",
        "verdict": "pass",
        "runtimeId": arguments.runtime_id,
        "device": {"abi": abi, "abiList": abi_list, "kernel": kernel, "sdk": sdk},
        "scope": {
            "nativeGraphLoaded": True,
            "frameworkAndMediaCodecExecuted": False,
            "compatibilitySymbols": compatibility_symbols,
            "stableReleaseMatrixSatisfied": sdk >= 28 and not compatibility_symbols,
        },
        "probe": probe,
        "libraries": [
            {"name": path.name, "sha256": digest(path)}
            for path in sorted(libraries, key=lambda item: item.name)
        ],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": "pass", "reportSha256": digest(arguments.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
