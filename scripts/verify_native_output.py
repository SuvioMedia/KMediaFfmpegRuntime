#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path


WINDOWS_SYSTEM_DLLS = frozenset({
    "bcrypt.dll",
    "crypt32.dll",
    "gdi32.dll",
    "kernel32.dll",
    "ncrypt.dll",
    "ole32.dll",
    "secur32.dll",
    "user32.dll",
    "ws2_32.dll",
})
WINDOWS_API_SET_PREFIXES = ("api-ms-win-", "ext-ms-win-")


def run(*command: str) -> str:
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE).stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator != "=" or not key or key in result:
            raise ValueError("runtime manifest contains a malformed or duplicate field")
        result[key] = value
    return result


def dependencies(path: Path, target: str, readelf: str) -> list[str]:
    if target.startswith(("macos-", "ios-")):
        return [line.strip().split(" (", 1)[0] for line in run("otool", "-L", str(path)).splitlines()[1:]]
    if target.startswith("windows-"):
        return re.findall(r"^\s*DLL Name:\s*(\S+)\s*$", run("objdump", "-p", str(path)), re.MULTILINE)
    return re.findall(r"\(NEEDED\).*?\[(.+?)\]", run(readelf, "-d", str(path)))


def verify_architecture(path: Path, target: str, readelf: str) -> None:
    if target.startswith(("macos-", "ios-")):
        if run("lipo", "-archs", str(path)).strip() != "arm64":
            raise ValueError(f"{path.name} is not exactly arm64")
    elif target.startswith("windows-"):
        if "pei-x86-64" not in run("objdump", "-f", str(path)):
            raise ValueError(f"{path.name} is not Windows x86_64")
    else:
        header = run(readelf, "-h", str(path))
        expected = "AArch64" if target.endswith(("aarch64", "arm64-v8a")) else "ARM" if target.endswith("armeabi-v7a") else "Advanced Micro Devices X86-64"
        if expected not in header:
            raise ValueError(f"{path.name} has the wrong ELF machine")


def verify_no_undefined_ffmpeg_internal_symbols(
    path: Path, target: str, readelf: str
) -> None:
    if target.startswith(("macos-", "ios-", "windows-")):
        return
    symbols = sorted(set(re.findall(
        r"\bUND\s+(ff_[A-Za-z0-9_]+)(?=@|\s|$)",
        run(readelf, "-Ws", str(path)),
    )))
    if symbols:
        raise ValueError(
            f"{path.name} retains undefined private FFmpeg symbols: {', '.join(symbols)}"
        )


def dynamic_symbols(path: Path, readelf: str) -> tuple[set[str], set[str]]:
    defined: set[str] = set()
    undefined: set[str] = set()
    for line in run(readelf, "--dyn-syms", "-W", str(path)).splitlines():
        fields = line.split()
        if len(fields) < 8 or not fields[0].endswith(":"):
            continue
        bind = fields[4]
        index = fields[6]
        if bind not in {"GLOBAL", "WEAK"}:
            continue
        name = fields[7].split("@", 1)[0]
        if not name:
            continue
        if index == "UND":
            if bind == "GLOBAL":
                undefined.add(name)
        else:
            defined.add(name)
    return defined, undefined


def is_elf(path: Path) -> bool:
    with path.open("rb") as source:
        return source.read(4) == b"\x7fELF"


def verify_android_symbol_closure(
    libraries: list[Path], target: str, readelf: str
) -> None:
    if not target.startswith("android-"):
        return
    triple = (
        "aarch64-linux-android"
        if target.endswith("arm64-v8a")
        else "arm-linux-androideabi"
    )
    stub_root = (
        Path(readelf).resolve().parent.parent
        / "sysroot" / "usr" / "lib" / triple / "23"
    )
    stubs = sorted(path for path in stub_root.glob("*.so") if is_elf(path))
    if not stubs:
        raise ValueError(f"Android API 23 NDK stubs are missing for {triple}")

    available: set[str] = set()
    unresolved_by_library: dict[str, set[str]] = {}
    for path in [*libraries, *stubs]:
        defined, undefined = dynamic_symbols(path, readelf)
        available.update(defined)
        if path in libraries:
            unresolved_by_library[path.name] = undefined

    missing = [
        f"{library} -> {symbol}"
        for library, undefined in sorted(unresolved_by_library.items())
        for symbol in sorted(undefined - available)
    ]
    if missing:
        details = "\n  ".join(missing)
        raise ValueError(
            "Android ELF graph contains strong symbols absent from both the packaged "
            f"runtime and API 23 NDK stubs:\n  {details}"
        )


def verify_windows_dependency_closure(
    graph: dict[str, list[str]], packaged: set[str], scope: str
) -> None:
    normalized_packaged = {name.casefold() for name in packaged}
    if len(normalized_packaged) != len(packaged):
        raise ValueError(f"{scope} contains case-colliding Windows DLL names")
    if {name.casefold() for name in graph} != normalized_packaged:
        raise ValueError(f"{scope} dependency graph differs from its DLL inventory")

    missing: list[str] = []
    for library, imported in sorted(graph.items()):
        if not imported:
            raise ValueError(f"objdump reported no imports for {library}")
        for dependency in imported:
            normalized = Path(dependency).name.casefold()
            is_api_set = normalized.startswith(WINDOWS_API_SET_PREFIXES)
            if (
                normalized not in normalized_packaged
                and normalized not in WINDOWS_SYSTEM_DLLS
                and not is_api_set
            ):
                missing.append(f"{library} -> {dependency}")
    if missing:
        details = "\n  ".join(missing)
        raise ValueError(
            f"{scope} imports DLLs outside the packaged runtime and Windows OS contract:\n"
            f"  {details}\nPATH-only dependencies are forbidden"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--readelf", default="readelf")
    args = parser.parse_args()
    manifest = properties(args.output / "runtime.properties")
    ass_manifest = properties(args.output / "ass-runtime.properties")
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?",
        manifest.get("distributionVersion", ""),
    ):
        raise ValueError("runtime manifest omits its immutable distribution version")
    if manifest.get("distributionVersion") != ass_manifest.get("distributionVersion"):
        raise ValueError("FFmpeg and ASS distribution versions differ")
    if manifest.get("assRuntimeId") != ass_manifest.get("runtimeId"):
        raise ValueError("FFmpeg manifest is not bound to the emitted ASS runtime")
    if not re.fullmatch(r"kmediaass-0\.17\.5-[0-9a-f]{16}", ass_manifest.get("runtimeId", "")):
        raise ValueError("ASS runtime ID is malformed")
    sdk_manifest = properties(args.output / "sdk" / args.target / "runtime.properties")
    sdk_ass_manifest = properties(args.output / "sdk" / args.target / "ass-runtime.properties")
    if sdk_manifest != manifest or sdk_ass_manifest != ass_manifest:
        raise ValueError("SDK and runtime manifests differ")
    ass_sdk = args.output / "ass" / "sdk" / args.target
    if properties(ass_sdk / "runtime.properties") != ass_manifest:
        raise ValueError("ASS-only SDK and runtime manifests differ")
    if (ass_sdk / "include/KMediaFfmpegRuntime.h").exists() or any(
        (ass_sdk / "include").glob("libav*")
    ):
        raise ValueError("ASS-only SDK exposes FFmpeg headers")
    ass_sdk_libraries = {
        path.name for path in (ass_sdk / "lib").iterdir()
        if path.is_file() and not path.name.endswith((".dll.a", ".lib"))
    }
    if ass_sdk_libraries != set(ass_manifest["libraries"].split(",")):
        raise ValueError("ASS-only SDK contains a foreign runtime library")
    if args.target.startswith("ios-"):
        expected_ass_frameworks = {
            "KMediaAssRuntime.framework",
            "KMediaFfmpegAss.framework",
            "KMediaFfmpegFreetype.framework",
            "KMediaFfmpegFribidi.framework",
            "KMediaFfmpegHarfbuzz.framework",
        }
        ass_framework_root = args.output / "ass" / "Frameworks"
        actual_ass_frameworks = {
            path.name for path in ass_framework_root.iterdir() if path.is_dir()
        }
        if actual_ass_frameworks != expected_ass_frameworks:
            raise ValueError("ASS-only iOS SDK has an incomplete or foreign framework inventory")
        for framework in ass_framework_root.iterdir():
            binary = framework / framework.stem
            if not binary.is_file():
                raise ValueError(f"{framework.name} omits its framework binary")
            verify_architecture(binary, args.target, args.readelf)
    inventories = (
        (args.output / "ass-runtime", ass_manifest, 5),
        (args.output / "ffmpeg-runtime", manifest, 7),
    )
    all_libraries: set[str] = set()
    runtime_library_paths: list[Path] = []
    windows_dependency_graph: dict[str, list[str]] = {}
    for runtime, scoped_manifest, expected_count in inventories:
        libraries = scoped_manifest["libraries"].split(",")
        files = {path.name for path in runtime.iterdir() if path.is_file() and not path.is_symlink()}
        if files != set(libraries) or len(libraries) != expected_count:
            raise ValueError("scoped runtime library inventory differs from the closed manifest")
        if all_libraries.intersection(libraries):
            raise ValueError("ASS and FFmpeg runtime artifacts overlap")
        all_libraries.update(libraries)
        for library in libraries:
            path = runtime / library
            runtime_library_paths.append(path)
            if scoped_manifest.get("sha256." + library) != sha256(path):
                raise ValueError(f"{library} hash differs from its manifest")
            verify_architecture(path, args.target, args.readelf)
            verify_no_undefined_ffmpeg_internal_symbols(path, args.target, args.readelf)
            library_dependencies = dependencies(path, args.target, args.readelf)
            if args.target.startswith("windows-"):
                windows_dependency_graph[library] = library_dependencies
            for dependency in library_dependencies:
                basename = Path(dependency).name
                if (
                    args.target.startswith(("macos-", "ios-"))
                    and "kmediaffmpeg" in basename
                    and not dependency.startswith("@rpath/")
                ):
                    raise ValueError(
                        f"{library} retains a non-relocatable Apple dependency: {dependency}")
                if "avcodec" in basename or "avfilter" in basename or "avformat" in basename \
                        or "avutil" in basename or "swresample" in basename \
                        or "swscale" in basename or "freetype" in basename \
                        or "fribidi" in basename or "harfbuzz" in basename \
                        or basename.startswith("libass"):
                    if "kmediaffmpeg" not in basename:
                        raise ValueError(
                            f"{library} retains a generic bundled dependency: {dependency}")
    verify_android_symbol_closure(runtime_library_paths, args.target, args.readelf)
    if args.target.startswith("windows-"):
        verify_windows_dependency_closure(
            windows_dependency_graph, all_libraries, "combined Windows runtime"
        )
        ass_libraries = set(ass_manifest["libraries"].split(","))
        verify_windows_dependency_closure(
            {
                library: windows_dependency_graph[library]
                for library in ass_libraries
            },
            ass_libraries,
            "standalone Windows ASS runtime",
        )
    avutil = next(
        args.output / "ffmpeg-runtime" / name
        for name in manifest["libraries"].split(",")
        if "avutil" in name
    )
    strings = run("strings", str(avutil))
    normalized_strings = strings.replace("'", "")
    for flag in ("--disable-gpl", "--disable-version3", "--disable-nonfree", "--enable-network", "--disable-static"):
        if flag not in normalized_strings:
            raise ValueError(f"compiled FFmpeg configuration is missing {flag}")
    if "--enable-protocol=crypto,file,http,https,httpproxy,pipe,tcp,tls" not in normalized_strings:
        raise ValueError("compiled FFmpeg configuration is missing the reviewed network protocols")
    tls_backend = (
        "--enable-openssl"
        if args.target.startswith(("android-", "linux-"))
        else "--enable-securetransport"
        if args.target.startswith(("macos-", "ios-"))
        else "--enable-schannel"
    )
    if tls_backend not in normalized_strings:
        raise ValueError(f"compiled FFmpeg configuration is missing {tls_backend}")
    for path in args.output.rglob("*"):
        if path.is_file() and path.suffix in {".a", ".o", ".obj"} and "sdk" not in path.parts:
            raise ValueError(f"runtime output contains a static artifact: {path}")
        if path.is_file() and path.name.lower().startswith(("libssl.", "libcrypto.")):
            raise ValueError(f"runtime output exposes a private TLS library: {path}")
    print(
        f"verified {args.target}: {manifest['runtimeId']} with {ass_manifest['runtimeId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
