#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Build one closed KMediaFfmpegRuntime target and its matching native SDK."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("freetype", "fribidi", "harfbuzz", "libass", "openssl", "ffmpeg")
ASS_COMPONENTS = ("freetype", "fribidi", "harfbuzz", "libass")
FFMPEG_COMPONENTS = ("openssl", "ffmpeg")
ASS_LOGICAL_LIBRARIES = ("freetype", "fribidi", "harfbuzz", "ass")
FFMPEG_LOGICAL_LIBRARIES = (
    "avutil", "swresample", "swscale", "avcodec", "avformat", "avfilter",
)
LOGICAL_LIBRARIES = FFMPEG_LOGICAL_LIBRARIES + ASS_LOGICAL_LIBRARIES
VERSIONS = {
    "ffmpeg": "9.0.1",
    "freetype": "2.14.1",
    "fribidi": "1.0.16",
    "harfbuzz": "12.2.0",
    "libass": "0.17.5",
    "openssl": "3.5.7",
}
LICENSES = {
    "ffmpeg": "LGPL-2.1-or-later",
    "freetype": "FTL",
    "fribidi": "LGPL-2.1-or-later",
    "harfbuzz": "MIT",
    "libass": "ISC",
    "openssl": "Apache-2.0",
}
ANDROID = {
    "android-arm64-v8a": {
        "abi": "arm64-v8a", "triple": "aarch64-linux-android", "arch": "aarch64",
        "cpu": "armv8-a", "meson_family": "aarch64", "meson_cpu": "armv8-a",
    },
    "android-armeabi-v7a": {
        "abi": "armeabi-v7a", "triple": "armv7a-linux-androideabi", "arch": "arm",
        "cpu": "armv7-a", "meson_family": "arm", "meson_cpu": "armv7-a",
    },
}
APPLE = {
    "ios-arm64": {"sdk": "iphoneos", "triple": "arm64-apple-ios16.2", "simulator": False},
    "ios-simulator-arm64": {"sdk": "iphonesimulator", "triple": "arm64-apple-ios16.2-simulator", "simulator": True},
}
FRAMEWORK_NAMES = {
    "avcodec": "KMediaFfmpegAvcodec",
    "avfilter": "KMediaFfmpegAvfilter",
    "avformat": "KMediaFfmpegAvformat",
    "avutil": "KMediaFfmpegAvutil",
    "swresample": "KMediaFfmpegSwresample",
    "swscale": "KMediaFfmpegSwscale",
    "freetype": "KMediaFfmpegFreetype",
    "fribidi": "KMediaFfmpegFribidi",
    "harfbuzz": "KMediaFfmpegHarfbuzz",
    "ass": "KMediaFfmpegAss",
    "ffmpeg-probe": "KMediaFfmpegRuntime",
    "ass-probe": "KMediaAssRuntime",
}


def run(*command: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    effective_command = command
    if env is not None:
        effective_command = ("env", *(f"{name}={value}" for name, value in sorted(env.items())), *command)
    print("+", " ".join(effective_command), flush=True)
    result = subprocess.run(
        effective_command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=None,
    )
    return result.stdout


def command_path(path: Path) -> str:
    """Return a path understood by POSIX tools invoked from MSYS Python."""
    if platform.system() == "Windows":
        return run("cygpath", "-u", str(path)).strip()
    return str(path)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, source_archives: Path | None = None) -> None:
    if destination.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_archives is not None:
        source = source_archives / destination.name
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"offline source input is missing: {source}")
        shutil.copyfile(source, destination)
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "KMediaFfmpegRuntime/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            temporary.replace(destination)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            temporary.unlink(missing_ok=True)
            if (
                attempt == 2
                or isinstance(error, urllib.error.HTTPError)
                and error.code not in {408, 425, 429, 500, 502, 503, 504}
            ):
                raise
            time.sleep(2 ** attempt)


def safe_extract(archive: Path, destination: Path) -> Path:
    if destination.exists():
        raise ValueError(f"source destination already exists: {destination}")
    temporary = destination.parent / (destination.name + ".extract")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    with tarfile.open(archive, "r:*") as source:
        for member in source.getmembers():
            pure = Path(member.name)
            if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk():
                raise ValueError(f"unsafe source archive entry: {member.name}")
        # Every entry was closed over above; Python 3.9 on Xcode runners does
        # not yet expose tarfile's newer extraction_filter argument.
        source.extractall(temporary)
    roots = [item for item in temporary.iterdir() if item.is_dir()]
    if len(roots) != 1:
        raise ValueError(f"{archive.name} does not contain exactly one source root")
    roots[0].replace(destination)
    temporary.rmdir()
    return destination


def verify_ffmpeg_signature(
    downloads: Path, policy: dict, source_archives: Path | None
) -> dict[str, str]:
    ffmpeg = load_json(ROOT / "compliance/components/ffmpeg.json")
    signature = downloads / (ffmpeg["sourceArchive"] + ".asc")
    key = downloads / "ffmpeg-devel.asc"
    download(ffmpeg["signatureUrl"], signature, source_archives)
    download("https://ffmpeg.org/ffmpeg-devel.asc", key, source_archives)
    with tempfile.TemporaryDirectory(prefix="kmediaffmpeg-gpg-") as value:
        home = Path(value)
        keyring = Path(value) / "ffmpeg-release-key.gpg"
        home_arg = command_path(home)
        key_arg = command_path(key)
        keyring_arg = command_path(keyring)
        signature_arg = command_path(signature)
        archive_arg = command_path(downloads / ffmpeg["sourceArchive"])
        fingerprints = run(
            "gpg", "--batch", "--no-autostart", "--homedir", home_arg,
            "--with-colons", "--show-keys", "--fingerprint", key_arg
        )
        expected = policy["ffmpegSigningFingerprint"]
        actual = {line.split(":")[9] for line in fingerprints.splitlines() if line.startswith("fpr:")}
        if expected not in actual:
            raise ValueError("FFmpeg signing key fingerprint differs from policy")
        run(
            "gpg", "--batch", "--no-autostart", "--homedir", home_arg,
            "--dearmor", "--output", keyring_arg, key_arg,
        )
        run(
            "gpgv", "--keyring", keyring_arg, signature_arg, archive_arg,
        )
    return {"signature": signature.name, "key": key.name, "fingerprint": policy["ffmpegSigningFingerprint"]}


def patch_once(path: Path, before: str, after: str, records: list[dict[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(before) != 1:
        raise ValueError(f"patch context is not unique in {path}")
    before_hash = hashlib.sha256(text.encode()).hexdigest()
    result = text.replace(before, after, 1)
    path.write_text(result, encoding="utf-8")
    records.append({
        "path": path.as_posix(),
        "beforeSha256": before_hash,
        "afterSha256": hashlib.sha256(result.encode()).hexdigest(),
    })


def namespace_sources(sources: Path, target: str, records: list[dict[str, str]]) -> None:
    prefix = "kmediaffmpeg"
    ffmpeg = sources / "ffmpeg"
    patch_once(
        ffmpeg / "configure",
        "        SLIB_INSTALL_NAME='$(SLIBNAME)'\n        SLIB_INSTALL_LINKS=\n",
        f"        SLIBPREF=\"lib{prefix}_\"\n        SLIB_INSTALL_NAME='$(SLIBNAME)'\n        SLIB_INSTALL_LINKS=\n",
        records,
    )
    for needle in (
        "Libs: -L\\${libdir} $rpath -l${fullname#lib} $($shared || echo $libs)",
        "Libs: -L\\${libdir} -Wl,-rpath,\\${libdir} -l${fullname#lib} $($shared || echo $libs)",
    ):
        patch_once(
            ffmpeg / "ffbuild/pkgconfig_generate.sh",
            needle,
            needle.replace("-l${fullname#lib}", f"-l{prefix}_${{fullname#lib}}"),
            records,
        )
    patch_once(sources / "freetype/meson.build", "ft2_lib = library('freetype',", f"ft2_lib = library('{prefix}_freetype',", records)
    patch_once(sources / "freetype/meson.build", "  version: ft2_so_version,\n", "", records)
    patch_once(sources / "fribidi/lib/meson.build", "libfribidi = library('fribidi',", f"libfribidi = library('{prefix}_fribidi',", records)
    patch_once(sources / "fribidi/lib/meson.build", "  version: libversion,\n  soversion: soversion,\n", "", records)
    harfbuzz = sources / "harfbuzz/src/meson.build"
    patch_once(harfbuzz, "libharfbuzz = library('harfbuzz', hb_sources,", f"libharfbuzz = library('{prefix}_harfbuzz', hb_sources,", records)
    patch_once(
        harfbuzz,
        f"libharfbuzz = library('{prefix}_harfbuzz', hb_sources,\n  include_directories: incconfig,\n  dependencies: harfbuzz_deps,\n  cpp_args: cpp_args + extra_hb_cpp_args,\n  soversion: hb_so_version,\n  version: version,\n",
        f"libharfbuzz = library('{prefix}_harfbuzz', hb_sources,\n  include_directories: incconfig,\n  dependencies: harfbuzz_deps,\n  cpp_args: cpp_args + extra_hb_cpp_args,\n",
        records,
    )
    patch_once(
        harfbuzz,
        "pkgmod.generate(libharfbuzz,\n  description: 'HarfBuzz text shaping library',\n",
        "pkgmod.generate(libharfbuzz,\n  filebase: 'harfbuzz',\n  description: 'HarfBuzz text shaping library',\n",
        records,
    )
    libass = sources / "libass/libass/meson.build"
    patch_once(libass, "    'ass',\n", f"    '{prefix}_ass',\n", records)
    patch_once(libass, "    version: libass_so_version,\n", "", records)
    subtitles_patch = ROOT / "native/patches/ffmpeg-9.0.1-subtitles-optional-wrap-unicode.patch"
    run("patch", "-p1", "--forward", "--input", str(subtitles_patch), cwd=ffmpeg)
    records.append({"path": subtitles_patch.relative_to(ROOT).as_posix(), "sha256": sha256(subtitles_patch)})
    if target.startswith("android-"):
        patch_file = ROOT / "native/patches/ffmpeg-9.0.1-mediacodec-p010.patch"
        run("patch", "-p1", "--forward", "--input", str(patch_file), cwd=ffmpeg)
        records.append({"path": patch_file.relative_to(ROOT).as_posix(), "sha256": sha256(patch_file)})


def target_platform(target: str) -> str:
    if target.startswith("android-"):
        return "android"
    if target.startswith("ios-"):
        return "ios"
    return target.split("-", 1)[0]


def apply_platform_patches(
    sources: Path, target: str, records: list[dict[str, str]]
) -> None:
    patch_root = (ROOT / "native/patches").resolve()
    platform_name = target_platform(target)
    for component in COMPONENTS:
        manifest = load_json(ROOT / f"compliance/components/{component}.json")
        for patch in manifest.get("platformPatches", {}).get(platform_name, []):
            relative = patch["path"]
            patch_file = (ROOT / relative).resolve()
            if patch_file.parent != patch_root or not patch_file.is_file():
                raise ValueError(f"{component}: invalid platform patch: {relative}")
            actual_hash = sha256(patch_file)
            if actual_hash != patch["sha256"]:
                raise ValueError(f"{component}: platform patch hash differs: {relative}")
            run(
                "patch", "-p1", "--forward", "--input", str(patch_file),
                cwd=sources / component,
            )
            records.append({
                "path": patch_file.relative_to(ROOT).as_posix(),
                "sha256": actual_hash,
            })


def prepare_sources(
    work: Path, target: str, source_archives: Path | None
) -> tuple[Path, Path, dict[str, str]]:
    downloads = work / "downloads"
    sources = work / "sources"
    downloads.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    policy = load_json(ROOT / "compliance/policy/release-policy.json")
    for component in COMPONENTS:
        manifest = load_json(ROOT / f"compliance/components/{component}.json")
        archive = downloads / manifest["sourceArchive"]
        download(manifest["sourceUrl"], archive, source_archives)
        if sha256(archive) != manifest["sourceSha256"]:
            raise ValueError(f"{component} source SHA-256 differs from policy")
        safe_extract(archive, sources / component)
    signature = verify_ffmpeg_signature(downloads, policy, source_archives)
    records: list[dict[str, str]] = []
    namespace_sources(sources, target, records)
    apply_platform_patches(sources, target, records)
    (work / "source-patches.json").write_text(json.dumps({"schemaVersion": 1, "patches": records}, indent=2) + "\n")
    return sources, downloads, signature


def quote(value: str) -> str:
    return "'" + value.replace("'", "\\'") + "'"


def meson_array(values: list[str]) -> str:
    return "[" + ", ".join(quote(item) for item in values) + "]"


def android_tools(ndk: Path, target: str) -> tuple[dict[str, str], dict]:
    details = ANDROID[target]
    host = platform.system().lower()
    host_tag = "darwin-x86_64" if host == "darwin" else "linux-x86_64"
    bin_dir = ndk / "toolchains/llvm/prebuilt" / host_tag / "bin"
    api = 23
    cc = bin_dir / f"{details['triple']}{api}-clang"
    tools = {
        "c": str(cc), "cpp": str(bin_dir / f"{details['triple']}{api}-clang++"),
        "ar": str(bin_dir / "llvm-ar"), "nm": str(bin_dir / "llvm-nm"),
        "ranlib": str(bin_dir / "llvm-ranlib"), "strip": str(bin_dir / "llvm-strip"),
        "readelf": str(bin_dir / "llvm-readelf"),
        "sysroot": str(ndk / "toolchains/llvm/prebuilt" / host_tag / "sysroot"),
    }
    for name, value in tools.items():
        if name != "sysroot" and not Path(value).is_file():
            raise ValueError(f"Android NDK tool is missing: {value}")
    return tools, details


def write_android_cross(path: Path, tools: dict[str, str], details: dict, prefix: Path, work: Path) -> None:
    mapping = str(work) + "=."
    compile_args = ["-fPIC", f"-ffile-prefix-map={mapping}", f"-fdebug-prefix-map={mapping}"]
    link_args = ["-Wl,--build-id=sha1", "-Wl,-z,relro", "-Wl,-z,now", "-Wl,-z,max-page-size=16384"]
    path.write_text("\n".join([
        "[binaries]",
        f"c = {quote(tools['c'])}", f"cpp = {quote(tools['cpp'])}", f"ar = {quote(tools['ar'])}",
        f"nm = {quote(tools['nm'])}", f"ranlib = {quote(tools['ranlib'])}", f"strip = {quote(tools['strip'])}",
        "pkg-config = 'pkg-config'", "", "[properties]", "needs_exe_wrapper = true",
        f"pkg_config_libdir = {quote(str(prefix / 'lib/pkgconfig'))}", "", "[host_machine]", "system = 'android'",
        f"cpu_family = {quote(details['meson_family'])}", f"cpu = {quote(details['meson_cpu'])}", "endian = 'little'", "",
        "[built-in options]", f"c_args = {meson_array(compile_args)}", f"cpp_args = {meson_array(compile_args)}",
        f"c_link_args = {meson_array(link_args)}", f"cpp_link_args = {meson_array(link_args + ['-static-libstdc++'])}",
    ]) + "\n")


def xcrun(sdk: str, *args: str) -> str:
    return run("xcrun", "--sdk", sdk, *args).strip()


def write_apple_cross(path: Path, target: str, prefix: Path, work: Path) -> tuple[dict[str, str], str]:
    details = APPLE[target]
    sdk = details["sdk"]
    sysroot = xcrun(sdk, "--show-sdk-path")
    tools = {name: xcrun(sdk, "--find", executable) for name, executable in {
        "c": "clang", "cpp": "clang++", "ar": "ar", "nm": "nm", "ranlib": "ranlib", "strip": "strip",
    }.items()}
    common = ["-target", details["triple"], "-isysroot", sysroot, "-fPIC", f"-ffile-prefix-map={work}=."]
    link = ["-target", details["triple"], "-isysroot", sysroot, "-Wl,-headerpad_max_install_names"]
    path.write_text("\n".join([
        "[binaries]", *(f"{name} = {quote(value)}" for name, value in tools.items()), "pkg-config = 'pkg-config'", "",
        "[built-in options]", f"c_args = {meson_array(common)}", f"cpp_args = {meson_array(common)}",
        f"c_link_args = {meson_array(link)}", f"cpp_link_args = {meson_array(link)}", "",
        "[properties]", "needs_exe_wrapper = true", f"pkg_config_libdir = {quote(str(prefix / 'lib/pkgconfig'))}", "",
        "[host_machine]", "system = 'darwin'", "cpu_family = 'aarch64'", "cpu = 'arm64'", "endian = 'little'",
    ]) + "\n")
    return tools, sysroot


def component_arguments(component: str, target: str) -> list[str]:
    manifest = load_json(ROOT / f"compliance/components/{component}.json")
    arguments = list(manifest.get("buildArguments", []))
    arguments.extend(manifest.get("platformArguments", {}).get(target_platform(target), []))
    return arguments


def build_meson(component: str, target: str, sources: Path, builds: Path, prefix: Path, cross: Path | None, env: dict[str, str]) -> None:
    command = ["meson", "setup", str(builds / component), str(sources / component), "--prefix", str(prefix)]
    if cross is not None:
        command.extend(["--cross-file", str(cross)])
    command.extend(component_arguments(component, target))
    run(*command, env=env)
    run("meson", "compile", "-C", str(builds / component), "-j", str(os.cpu_count() or 4), env=env)
    run("meson", "install", "-C", str(builds / component), env=env)


def build_openssl(
    target: str,
    sources: Path,
    prefix: Path,
    tools: dict[str, str] | None,
    ndk: Path | None,
    env: dict[str, str],
) -> None:
    if not (target.startswith("android-") or target.startswith("linux-")):
        return
    configure_target = {
        "android-arm64-v8a": "android-arm64",
        "android-armeabi-v7a": "android-arm",
        "linux-x86_64": "linux-x86_64",
        "linux-aarch64": "linux-aarch64",
    }[target]
    openssl_env = dict(env)
    if target.startswith("android-"):
        assert tools is not None and ndk is not None
        openssl_env["ANDROID_NDK_ROOT"] = str(ndk)
        openssl_env["PATH"] = (
            str(Path(tools["c"]).parent) + os.pathsep + os.environ.get("PATH", "")
        )
    arguments = [
        "./Configure", configure_target, "--prefix=/", "--openssldir=/ssl", "--libdir=lib",
        "no-shared", "no-tests", "no-apps", "no-docs", "no-module", "no-legacy",
        "-fPIC",
    ]
    run(*arguments, cwd=sources / "openssl", env=openssl_env)
    run("make", "-j", str(os.cpu_count() or 4), "build_libs", cwd=sources / "openssl", env=openssl_env)
    run("make", "install_sw", f"DESTDIR={prefix}", cwd=sources / "openssl", env=openssl_env)


def ffmpeg_arguments(target: str) -> list[str]:
    manifest = load_json(ROOT / "compliance/components/ffmpeg.json")
    arguments = list(manifest["buildArguments"])
    arguments.extend(manifest.get("platformArguments", {}).get(target_platform(target), []))
    if target == "windows-x86_64":
        arguments.extend([
            "--disable-pthreads", "--enable-w32threads",
            "--extra-ldflags=-no-pthread -static-libgcc",
            "--extra-libs=-Wl,-Bstatic -lwinpthread -Wl,-Bdynamic,--exclude-libs,libwinpthread.a",
        ])
    return arguments


def build_ffmpeg(
    target: str,
    sources: Path,
    prefix: Path,
    env: dict[str, str],
    tools: dict[str, str] | None,
    details: dict | None,
    sysroot: str | None,
) -> list[str]:
    arguments = [f"--prefix={prefix}", *ffmpeg_arguments(target)]
    if target.startswith("android-"):
        assert tools is not None and details is not None
        arguments.extend([
            "--target-os=android", "--enable-cross-compile", f"--arch={details['arch']}", f"--cpu={details['cpu']}",
            f"--cc={tools['c']}", f"--cxx={tools['cpp']}", f"--ar={tools['ar']}", f"--nm={tools['nm']}",
            f"--ranlib={tools['ranlib']}", f"--strip={tools['strip']}", f"--sysroot={tools['sysroot']}",
            f"--extra-cflags=-fPIC -I{prefix / 'include'}",
            f"--extra-ldflags=-L{prefix / 'lib'} -Wl,-z,relro -Wl,-z,now -Wl,-z,max-page-size=16384",
            "--extra-libs=-lssl -lcrypto -ldl -lmediandk -landroid -llog",
        ])
    elif target.startswith("linux-"):
        arguments.extend([
            f"--extra-cflags=-I{prefix / 'include'}",
            f"--extra-ldflags=-L{prefix / 'lib'}",
            "--extra-libs=-lssl -lcrypto -ldl -pthread",
        ])
    elif target.startswith("ios-"):
        assert tools is not None and details is not None and sysroot is not None
        arguments.extend([
            "--target-os=darwin", "--enable-cross-compile", "--arch=arm64", "--enable-pic", "--disable-asm",
            f"--cc={tools['c']}", f"--cxx={tools['cpp']}", f"--ar={tools['ar']}", f"--nm={tools['nm']}",
            f"--ranlib={tools['ranlib']}", f"--strip={tools['strip']}", f"--sysroot={sysroot}",
            f"--extra-cflags=-target {details['triple']} -isysroot {sysroot}",
            f"--extra-ldflags=-target {details['triple']} -isysroot {sysroot} -Wl,-headerpad_max_install_names",
        ])
    run("./configure", *arguments, cwd=sources / "ffmpeg", env=env)
    make_arguments = ["SLIBPREF=libkmediaffmpeg_", "LD_LIB=-lkmediaffmpeg_%"]
    run("make", "-j", str(os.cpu_count() or 4), *make_arguments, cwd=sources / "ffmpeg", env=env)
    run("make", "install", *make_arguments, cwd=sources / "ffmpeg", env=env)
    return arguments


def find_library(prefix: Path, logical: str, target: str) -> Path:
    roots = [prefix / "bin", prefix / "lib"] if target.startswith("windows-") else [prefix / "lib"]
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob(f"*kmediaffmpeg_{logical}*"):
            if target.startswith("windows-"):
                is_runtime = path.suffix.lower() == ".dll"
            else:
                is_runtime = not path.name.endswith((".a", ".dll.a", ".lib"))
            if path.is_file() and not path.is_symlink() and is_runtime:
                candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(f"{logical}: expected one namespaced real library, got {[item.name for item in candidates]}")
    return candidates[0]


def destination_name(logical: str, target: str, source: Path) -> str:
    if target.startswith("windows-"):
        return source.name
    if target.startswith("macos-") or target.startswith("ios-"):
        return f"libkmediaffmpeg_{logical}.dylib"
    return f"libkmediaffmpeg_{logical}.so"


def copy_and_rewrite_runtime(prefix: Path, runtime: Path, target: str) -> dict[str, str]:
    runtime.mkdir(parents=True, exist_ok=True)
    originals: dict[str, str] = {}
    outputs: dict[str, str] = {}
    for logical in LOGICAL_LIBRARIES:
        source = find_library(prefix, logical, target)
        destination = destination_name(logical, target, source)
        shutil.copyfile(source, runtime / destination)
        for root in (prefix / "lib", prefix / "bin"):
            if root.is_dir():
                for installed in root.glob(f"*kmediaffmpeg_{logical}*"):
                    originals[installed.name] = destination
        originals[source.name] = destination
        outputs[logical] = destination
    if target.startswith("linux-") or target.startswith("android-"):
        patchelf = shutil.which("patchelf")
        if target.startswith("linux-") and patchelf is None:
            raise ValueError("patchelf is required for Linux runtime canonicalization")
        if patchelf:
            for name in outputs.values():
                path = runtime / name
                run(patchelf, "--set-soname", name, str(path))
            for name in outputs.values():
                path = runtime / name
                needed = run(patchelf, "--print-needed", str(path)).splitlines()
                for dependency in needed:
                    replacement = originals.get(Path(dependency).name)
                    if replacement and replacement != dependency:
                        run(patchelf, "--replace-needed", dependency, replacement, str(path))
                if target.startswith("linux-"):
                    run(patchelf, "--set-rpath", "$ORIGIN", str(path))
    elif target.startswith("macos-") or target.startswith("ios-"):
        for name in outputs.values():
            path = runtime / name
            run("install_name_tool", "-id", f"@rpath/{name}", str(path))
            if target.startswith("macos-"):
                run("install_name_tool", "-add_rpath", "@loader_path", str(path))
        for name in outputs.values():
            path = runtime / name
            dependencies = [line.strip().split(" (", 1)[0] for line in run("otool", "-L", str(path)).splitlines()[1:]]
            for dependency in dependencies:
                replacement = originals.get(Path(dependency).name)
                if replacement and dependency != f"@rpath/{replacement}":
                    run("install_name_tool", "-change", dependency, f"@rpath/{replacement}", str(path))
    return outputs


def ass_configuration_identity(target: str) -> tuple[str, str]:
    versions = {component: VERSIONS[component] for component in ASS_COMPONENTS}
    licenses = {component: LICENSES[component] for component in ASS_COMPONENTS}
    build_arguments = {
        component: component_arguments(component, target)
        for component in ASS_COMPONENTS
    }
    configuration_material = {
        "schemaVersion": 1,
        "target": target,
        "versions": versions,
        "licenses": licenses,
        "buildArguments": build_arguments,
    }
    configuration = hashlib.sha256(
        json.dumps(configuration_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    identity_material = {
        "schemaVersion": 1,
        "versions": versions,
        "licenses": licenses,
        "sources": {
            component: load_json(ROOT / f"compliance/components/{component}.json")["sourceSha256"]
            for component in ASS_COMPONENTS
        },
        "buildPolicy": {
            component: load_json(ROOT / f"compliance/components/{component}.json")
            for component in ASS_COMPONENTS
        },
    }
    identity = hashlib.sha256(
        json.dumps(identity_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"kmediaass-{VERSIONS['libass']}-{identity[:16]}", configuration


def configuration_identity(
    target: str, arguments: list[str], ass_runtime_id: str | None = None
) -> tuple[str, str]:
    if ass_runtime_id is None:
        ass_runtime_id = ass_configuration_identity(target)[0]
    configuration_material = {
        "schemaVersion": 1,
        "target": target,
        "versions": VERSIONS,
        "licenses": LICENSES,
        "assRuntimeId": ass_runtime_id,
        "ffmpegArguments": arguments,
    }
    configuration = hashlib.sha256(
        json.dumps(configuration_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # The runtime ID identifies the release-wide ABI contract and therefore has to be
    # identical on every target. Target-specific configure arguments remain bound by
    # configurationSha256 in each manifest.
    identity_material = {
        "schemaVersion": 1,
        "versions": VERSIONS,
        "licenses": LICENSES,
        "assRuntimeId": ass_runtime_id,
        "policy": load_json(ROOT / "compliance/policy/release-policy.json"),
        "sources": {
            component: load_json(ROOT / f"compliance/components/{component}.json")["sourceSha256"]
            for component in COMPONENTS
        },
    }
    identity = hashlib.sha256(
        json.dumps(identity_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return (
        f"kmediaffmpeg-{VERSIONS['ffmpeg']}-ass-{VERSIONS['libass']}-{identity[:16]}",
        configuration,
    )


def write_identity_header(path: Path, runtime_id: str, configuration: str) -> None:
    path.write_text(
        "#pragma once\n"
        f"#define KMEDIAFFMPEG_RUNTIME_ID \"{runtime_id}\"\n"
        f"#define KMEDIAFFMPEG_CONFIGURATION_SHA256 \"{configuration}\"\n"
    )


def write_ass_identity_header(path: Path, runtime_id: str, configuration: str) -> None:
    path.write_text(
        "#pragma once\n"
        f"#define KMEDIAASS_RUNTIME_ID \"{runtime_id}\"\n"
        f"#define KMEDIAASS_CONFIGURATION_SHA256 \"{configuration}\"\n"
    )


def write_runtime_id(path: Path, runtime_id: str) -> None:
    path.write_bytes((runtime_id + "\n").encode("ascii"))


def desktop_java_home() -> Path:
    if platform.system() == "Darwin":
        return Path(run("/usr/libexec/java_home").strip())
    configured = os.environ.get("JAVA_HOME")
    if configured:
        return Path(configured)
    javac = shutil.which("javac")
    return Path(javac).resolve().parents[1] if javac is not None else Path("/__missing_java_home__")


def windows_import_library(prefix: Path, logical: str) -> Path:
    library_dir = prefix / "lib"
    for ending in (".dll.a", ".lib", ".def"):
        candidates = sorted(
            path for path in library_dir.glob(f"*kmediaffmpeg_{logical}*{ending}") if path.is_file()
        )
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ValueError(f"{logical}: multiple Windows import inputs ending in {ending}")
    raise ValueError(f"{logical}: Windows import library or definition file is missing")


def compile_probe(
    target: str,
    runtime: Path,
    prefix: Path,
    work: Path,
    runtime_id: str,
    configuration: str,
    tools: dict[str, str] | None,
    details: dict | None,
    sysroot: str | None,
) -> str:
    generated = work / "generated"
    generated.mkdir(exist_ok=True)
    write_identity_header(generated / "runtime_identity.h", runtime_id, configuration)
    if target.startswith("ios-"):
        source = ROOT / "native/probe/kmediaffmpeg_probe_apple.c"
        output = runtime / "libkmediaffmpeg_probe.dylib"
        assert tools is not None and details is not None and sysroot is not None
        run(
            tools["c"], "-dynamiclib", "-fPIC", "-target", details["triple"], "-isysroot", sysroot,
            "-I", str(generated), "-I", str(prefix / "include"), str(source),
            "-L", str(runtime), "-lkmediaffmpeg_avutil",
            "-Wl,-headerpad_max_install_names",
            "-Wl,-install_name,@rpath/libkmediaffmpeg_probe.dylib", "-o", str(output),
        )
        return output.name
    source = ROOT / "native/probe/kmediaffmpeg_probe.c"
    if target.startswith("android-"):
        output = runtime / "libkmediaffmpeg_probe.so"
        assert tools is not None
        run(
            tools["c"], "-shared", "-fPIC", "-I", str(generated), "-I", str(prefix / "include"),
            str(source), "-L", str(runtime), "-lkmediaffmpeg_avutil", "-llog",
            "-Wl,-soname,libkmediaffmpeg_probe.so", "-Wl,-z,relro", "-Wl,-z,now", "-o", str(output),
        )
        return output.name
    java_home = desktop_java_home()
    if not java_home.is_dir():
        raise ValueError("JAVA_HOME is required to build the desktop JNI probe")
    includes = ["-I", str(generated), "-I", str(prefix / "include"), "-I", str(java_home / "include")]
    if target.startswith("linux-"):
        output = runtime / "libkmediaffmpeg_probe.so"
        run("cc", "-shared", "-fPIC", *includes, "-I", str(java_home / "include/linux"), str(source),
            "-L", str(runtime), "-lkmediaffmpeg_avutil", "-Wl,-rpath,$ORIGIN",
            "-Wl,-soname,libkmediaffmpeg_probe.so", "-o", str(output))
    elif target.startswith("macos-"):
        output = runtime / "libkmediaffmpeg_probe.dylib"
        run("cc", "-dynamiclib", "-fPIC", *includes, "-I", str(java_home / "include/darwin"), str(source),
            "-L", str(runtime), "-lkmediaffmpeg_avutil", "-Wl,-rpath,@loader_path",
            "-Wl,-install_name,@rpath/libkmediaffmpeg_probe.dylib", "-o", str(output))
    else:
        output = runtime / "kmediaffmpeg_probe.dll"
        avutil_import = windows_import_library(prefix, "avutil")
        run("cc", "-shared", *includes, "-I", str(java_home / "include/win32"), str(source),
            str(avutil_import), "-o", str(output))
    return output.name


def compile_ass_probe(
    target: str,
    runtime: Path,
    prefix: Path,
    work: Path,
    runtime_id: str,
    configuration: str,
    tools: dict[str, str] | None,
    details: dict | None,
    sysroot: str | None,
) -> str:
    generated = work / "generated"
    generated.mkdir(exist_ok=True)
    write_ass_identity_header(generated / "ass_runtime_identity.h", runtime_id, configuration)
    if target.startswith("ios-"):
        source = ROOT / "native/probe/kmediaass_probe_apple.c"
        output = runtime / "libkmediaffmpeg_ass_probe.dylib"
        assert tools is not None and details is not None and sysroot is not None
        run(
            tools["c"], "-dynamiclib", "-fPIC", "-target", details["triple"], "-isysroot", sysroot,
            "-I", str(generated), "-I", str(prefix / "include"), str(source),
            "-L", str(runtime), "-lkmediaffmpeg_ass",
            "-Wl,-headerpad_max_install_names",
            "-Wl,-install_name,@rpath/libkmediaffmpeg_ass_probe.dylib", "-o", str(output),
        )
        return output.name
    source = ROOT / "native/probe/kmediaass_probe.c"
    if target.startswith("android-"):
        output = runtime / "libkmediaffmpeg_ass_probe.so"
        assert tools is not None
        run(
            tools["c"], "-shared", "-fPIC", "-I", str(generated), "-I", str(prefix / "include"),
            str(source), "-L", str(runtime), "-lkmediaffmpeg_ass", "-llog",
            "-Wl,-soname,libkmediaffmpeg_ass_probe.so", "-Wl,-z,relro", "-Wl,-z,now",
            "-o", str(output),
        )
        return output.name
    java_home = desktop_java_home()
    if not java_home.is_dir():
        raise ValueError("JAVA_HOME is required to build the desktop JNI probe")
    includes = ["-I", str(generated), "-I", str(prefix / "include"), "-I", str(java_home / "include")]
    if target.startswith("linux-"):
        output = runtime / "libkmediaffmpeg_ass_probe.so"
        run(
            "cc", "-shared", "-fPIC", *includes, "-I", str(java_home / "include/linux"), str(source),
            "-L", str(runtime), "-lkmediaffmpeg_ass", "-Wl,-rpath,$ORIGIN",
            "-Wl,-soname,libkmediaffmpeg_ass_probe.so", "-o", str(output),
        )
    elif target.startswith("macos-"):
        output = runtime / "libkmediaffmpeg_ass_probe.dylib"
        run(
            "cc", "-dynamiclib", "-fPIC", *includes, "-I", str(java_home / "include/darwin"), str(source),
            "-L", str(runtime), "-lkmediaffmpeg_ass", "-Wl,-rpath,@loader_path",
            "-Wl,-install_name,@rpath/libkmediaffmpeg_ass_probe.dylib", "-o", str(output),
        )
    else:
        output = runtime / "kmediaffmpeg_ass_probe.dll"
        ass_import = windows_import_library(prefix, "ass")
        run(
            "cc", "-shared", *includes, "-I", str(java_home / "include/win32"), str(source),
            str(ass_import), "-o", str(output),
        )
    return output.name


def write_manifest(
    path: Path,
    target: str,
    distribution_version: str,
    runtime_id: str,
    configuration: str,
    runtime: Path,
    libraries: list[str],
    components: tuple[str, ...] = COMPONENTS,
    ass_runtime_id: str | None = None,
) -> None:
    platform_name = "android" if target.startswith("android-") else target.split("-", 1)[0]
    abi = ANDROID[target]["abi"] if target in ANDROID else "aarch64" if target.endswith("aarch64") else "arm64" if target.startswith("ios-") else "x86_64"
    lines = [
        f"distributionVersion={distribution_version}",
        f"runtimeId={runtime_id}", f"platform={platform_name}", f"abi={abi}",
        f"configurationSha256={configuration}", f"libraries={','.join(libraries)}",
    ]
    if ass_runtime_id is not None:
        lines.append(f"assRuntimeId={ass_runtime_id}")
        for feature, enabled in ffmpeg_runtime_features(target).items():
            lines.append(f"feature.{feature}={str(enabled).lower()}")
    for component in sorted(components):
        lines.extend([f"version.{component}={VERSIONS[component]}", f"license.{component}={LICENSES[component]}"])
    for library in libraries:
        lines.append(f"sha256.{library}={sha256(runtime / library)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def ffmpeg_runtime_features(target: str) -> dict[str, bool]:
    full_desktop_transcode = target in {"macos-aarch64", "windows-x86_64"}
    return {
        "networkInput": True,
        "httpsInput": True,
        "hdrToSdrToneMap": target in ANDROID or full_desktop_transcode,
        "subtitleBurnIn": full_desktop_transcode,
        "avcAacTranscode": full_desktop_transcode,
    }


def copy_sdk(
    prefix: Path,
    runtime: Path,
    output: Path,
    target: str,
    manifest: Path,
    ass_manifest: Path | None = None,
    ass_only: bool = False,
) -> None:
    sdk = output / "sdk" / target
    if ass_only:
        for directory in ("ass", "freetype2", "fribidi", "harfbuzz"):
            source = prefix / "include" / directory
            if source.is_dir():
                shutil.copytree(source, sdk / "include" / directory, dirs_exist_ok=True)
    else:
        shutil.copytree(prefix / "include", sdk / "include", dirs_exist_ok=True)
        shutil.rmtree(sdk / "include/openssl", ignore_errors=True)
    shutil.copyfile(
        ROOT / "native/probe/KMediaAssRuntime.h",
        sdk / "include/KMediaAssRuntime.h",
    )
    if not ass_only:
        shutil.copyfile(
            ROOT / "native/probe/KMediaFfmpegRuntime.h",
            sdk / "include/KMediaFfmpegRuntime.h",
        )
    shutil.copytree(runtime, sdk / "lib", dirs_exist_ok=True)
    ass_import_names = {
        f"libkmediaffmpeg_{logical}.dll.a" for logical in ASS_LOGICAL_LIBRARIES
    }
    ass_pc_names = {
        "freetype2.pc", "fribidi.pc", "harfbuzz.pc", "harfbuzz-subset.pc", "libass.pc",
    }
    for source in (prefix / "lib", prefix / "bin"):
        if source.is_dir():
            for pattern in ("*.dll.a", "*.lib", "*.pc"):
                for path in source.rglob(pattern):
                    if path.name in {"libcrypto.pc", "libssl.pc", "openssl.pc"}:
                        continue
                    if ass_only and (
                        (path.suffix == ".pc" and path.name not in ass_pc_names)
                        or (path.suffix != ".pc" and path.name not in ass_import_names)
                    ):
                        continue
                    destination = sdk / ("pkgconfig" if path.suffix == ".pc" else "lib") / path.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if path.suffix == ".pc":
                        text = path.read_text(encoding="utf-8")
                        lines = text.splitlines()
                        rewritten = []
                        for line in lines:
                            if line.startswith("prefix="):
                                rewritten.append("prefix=${pcfiledir}/..")
                            elif line.startswith("libdir="):
                                rewritten.append("libdir=${prefix}/lib")
                            elif line.startswith("includedir="):
                                rewritten.append("includedir=${prefix}/include")
                            else:
                                rewritten.append(line)
                        destination.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
                    else:
                        shutil.copyfile(path, destination)
    shutil.copyfile(manifest, sdk / "runtime.properties")
    if ass_manifest is not None:
        shutil.copyfile(ass_manifest, sdk / "ass-runtime.properties")


def package_ios_frameworks(runtime: Path, output: Path, target: str) -> None:
    frameworks = output / "Frameworks"
    frameworks.mkdir(parents=True, exist_ok=True)
    binaries: dict[str, tuple[Path, str]] = {}
    for logical, framework_name in FRAMEWORK_NAMES.items():
        if logical == "ffmpeg-probe":
            source_name = "libkmediaffmpeg_probe.dylib"
        elif logical == "ass-probe":
            source_name = "libkmediaffmpeg_ass_probe.dylib"
        else:
            source_name = f"libkmediaffmpeg_{logical}.dylib"
        source = runtime / source_name
        framework = frameworks / f"{framework_name}.framework"
        headers = framework / "Headers"
        modules = framework / "Modules"
        headers.mkdir(parents=True)
        modules.mkdir()
        binary = framework / framework_name
        shutil.copyfile(source, binary)
        header_name = framework_name + ".h"
        if logical == "ffmpeg-probe":
            shutil.copyfile(ROOT / "native/probe/KMediaFfmpegRuntime.h", headers / header_name)
        elif logical == "ass-probe":
            shutil.copyfile(ROOT / "native/probe/KMediaAssRuntime.h", headers / header_name)
        else:
            (headers / header_name).write_text("#pragma once\n")
        (modules / "module.modulemap").write_text(
            f"framework module {framework_name} {{\n  umbrella header \"{header_name}\"\n  export *\n}}\n"
        )
        plist = {
            "CFBundleDevelopmentRegion": "en", "CFBundleExecutable": framework_name,
            "CFBundleIdentifier": f"cc.suviomedia.kmediaffmpeg.{framework_name.lower()}",
            "CFBundleInfoDictionaryVersion": "6.0", "CFBundleName": framework_name,
            "CFBundlePackageType": "FMWK", "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "1", "MinimumOSVersion": "16.2",
        }
        with (framework / "Info.plist").open("wb") as destination:
            plistlib.dump(plist, destination, sort_keys=True)
        binaries[source_name] = (binary, framework_name)
    for source_name, (binary, framework_name) in binaries.items():
        run("install_name_tool", "-id", f"@rpath/{framework_name}.framework/{framework_name}", str(binary))
        dependencies = [line.strip().split(" (", 1)[0] for line in run("otool", "-L", str(binary)).splitlines()[1:]]
        for dependency in dependencies:
            match = binaries.get(Path(dependency).name)
            if match:
                run("install_name_tool", "-change", dependency, f"@rpath/{match[1]}.framework/{match[1]}", str(binary))
    ass_frameworks = output / "ass" / "Frameworks"
    ass_frameworks.mkdir(parents=True, exist_ok=True)
    for logical in (*ASS_LOGICAL_LIBRARIES, "ass-probe"):
        framework_name = FRAMEWORK_NAMES[logical]
        shutil.copytree(
            frameworks / f"{framework_name}.framework",
            ass_frameworks / f"{framework_name}.framework",
        )


def write_evidence(
    output: Path,
    target: str,
    ffmpeg_args: list[str],
    signature: dict[str, str],
    downloads: Path,
    work: Path,
) -> None:
    evidence = output / "compliance"
    (evidence / "sources").mkdir(parents=True, exist_ok=True)
    for component in COMPONENTS:
        manifest = load_json(ROOT / f"compliance/components/{component}.json")
        shutil.copyfile(downloads / manifest["sourceArchive"], evidence / "sources" / manifest["sourceArchive"])
    (evidence / "build-arguments").mkdir(parents=True)
    (evidence / "build-arguments" / "ffmpeg.txt").write_text("\n".join(ffmpeg_args) + "\n")
    shutil.copyfile(work / "source-patches.json", evidence / "source-patches.json")
    (evidence / "signature-verification.json").write_text(json.dumps(signature, indent=2) + "\n")
    shutil.copyfile(ROOT / "compliance/policy/release-policy.json", evidence / "release-policy.json")
    (evidence / "target.json").write_text(json.dumps({"schemaVersion": 1, "target": target}, indent=2) + "\n")


def validate_host_target(target: str) -> None:
    machine = platform.machine().lower()
    system = platform.system().lower()
    if target == "linux-x86_64" and not (system == "linux" and machine in {"x86_64", "amd64"}):
        raise ValueError("linux-x86_64 must be built on Linux x86_64")
    if target == "linux-aarch64" and not (system == "linux" and machine in {"aarch64", "arm64"}):
        raise ValueError("linux-aarch64 must be built on Linux ARM64")
    if target == "macos-aarch64" and not (system == "darwin" and machine in {"aarch64", "arm64"}):
        raise ValueError("macos-aarch64 must be built on Apple Silicon")
    if target == "windows-x86_64" and not (
        system.startswith(("windows", "mingw", "msys")) and machine in {"x86_64", "amd64"}
    ):
        raise ValueError("windows-x86_64 must be built on a matching MSYS2 UCRT64 host")
    if target.startswith("ios-") and system != "darwin":
        raise ValueError("Apple slices must be built on macOS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(load_json(ROOT / "compliance/policy/release-policy.json")["targets"]), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ndk", type=Path)
    parser.add_argument(
        "--source-archives", type=Path,
        help="offline directory containing all pinned source archives and FFmpeg signature inputs",
    )
    args = parser.parse_args()
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?",
        args.version,
    ):
        raise ValueError("version must be immutable SemVer")
    validate_host_target(args.target)
    work = args.work.resolve()
    output = args.output.resolve()
    if work.exists() or output.exists():
        raise ValueError("work and output directories must not already exist")
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    sources, downloads, signature = prepare_sources(
        work,
        args.target,
        args.source_archives.resolve() if args.source_archives is not None else None,
    )
    prefix = work / "prefix"
    builds = work / "builds"
    prefix.mkdir()
    builds.mkdir()
    env = {
        "LC_ALL": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": "1767225600", "ZERO_AR_DATE": "1",
        "PKG_CONFIG_PATH": str(prefix / "lib/pkgconfig"), "PKG_CONFIG_LIBDIR": str(prefix / "lib/pkgconfig"),
    }
    cross: Path | None = None
    tools: dict[str, str] | None = None
    details: dict | None = None
    sysroot: str | None = None
    if args.target.startswith("android-"):
        if args.ndk is None:
            raise ValueError("--ndk is required for Android")
        tools, details = android_tools(args.ndk.resolve(), args.target)
        cross = work / "android-cross.ini"
        write_android_cross(cross, tools, details, prefix, work)
    elif args.target.startswith("ios-"):
        cross = work / "apple-cross.ini"
        tools, sysroot = write_apple_cross(cross, args.target, prefix, work)
        details = APPLE[args.target]
    for component in ("freetype", "fribidi", "harfbuzz", "libass"):
        build_meson(component, args.target, sources, builds, prefix, cross, env)
    build_openssl(
        args.target,
        sources,
        prefix,
        tools,
        args.ndk.resolve() if args.ndk is not None else None,
        env,
    )
    ffmpeg_args = build_ffmpeg(args.target, sources, prefix, env, tools, details, sysroot)
    combined_runtime = work / "canonical-runtime"
    library_names = copy_and_rewrite_runtime(prefix, combined_runtime, args.target)
    ass_runtime_id, ass_configuration = ass_configuration_identity(args.target)
    runtime_id, configuration = configuration_identity(args.target, ffmpeg_args, ass_runtime_id)
    ass_probe_name = compile_ass_probe(
        args.target, combined_runtime, prefix, work, ass_runtime_id, ass_configuration,
        tools, details, sysroot,
    )
    probe_name = compile_probe(
        args.target, combined_runtime, prefix, work, runtime_id, configuration,
        tools, details, sysroot,
    )
    ass_runtime = output / "ass-runtime"
    ffmpeg_runtime = output / "ffmpeg-runtime"
    ass_runtime.mkdir()
    ffmpeg_runtime.mkdir()
    ass_libraries = [library_names[name] for name in ASS_LOGICAL_LIBRARIES] + [ass_probe_name]
    ffmpeg_libraries = [library_names[name] for name in FFMPEG_LOGICAL_LIBRARIES] + [probe_name]
    for name in ass_libraries:
        shutil.copyfile(combined_runtime / name, ass_runtime / name)
    for name in ffmpeg_libraries:
        shutil.copyfile(combined_runtime / name, ffmpeg_runtime / name)
    ass_manifest = output / "ass-runtime.properties"
    write_manifest(
        ass_manifest, args.target, args.version, ass_runtime_id, ass_configuration,
        ass_runtime, ass_libraries, ASS_COMPONENTS,
    )
    manifest = output / "runtime.properties"
    write_manifest(
        manifest, args.target, args.version, runtime_id, configuration,
        ffmpeg_runtime, ffmpeg_libraries, COMPONENTS, ass_runtime_id,
    )
    sdk_runtime = work / "sdk-runtime"
    shutil.copytree(ass_runtime, sdk_runtime)
    shutil.copytree(ffmpeg_runtime, sdk_runtime, dirs_exist_ok=True)
    copy_sdk(prefix, sdk_runtime, output, args.target, manifest, ass_manifest)
    copy_sdk(prefix, ass_runtime, output / "ass", args.target, ass_manifest, ass_only=True)
    if args.target.startswith("ios-"):
        package_ios_frameworks(combined_runtime, output, args.target)
    write_evidence(output, args.target, ffmpeg_args, signature, downloads, work)
    write_runtime_id(output / "runtime-id.txt", runtime_id)
    write_runtime_id(output / "ass-runtime-id.txt", ass_runtime_id)
    verification = [
        sys.executable, "-B", str(ROOT / "scripts/verify_native_output.py"),
        "--output", str(output), "--target", args.target,
    ]
    if args.target.startswith("android-"):
        assert tools is not None
        verification.extend(["--readelf", tools["readelf"]])
    run(*verification)
    print(runtime_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
