#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ("linux-x86_64", "linux-aarch64", "macos-aarch64", "windows-x86_64")
APPLE_FFMPEG_FRAMEWORKS = (
    "KMediaFfmpegAvcodec", "KMediaFfmpegAvfilter", "KMediaFfmpegAvformat",
    "KMediaFfmpegAvutil", "KMediaFfmpegSwresample", "KMediaFfmpegSwscale",
    "KMediaFfmpegRuntime",
)
APPLE_ASS_FRAMEWORKS = (
    "KMediaFfmpegFreetype", "KMediaFfmpegFribidi", "KMediaFfmpegHarfbuzz",
    "KMediaFfmpegAss", "KMediaAssRuntime",
)


def clean_destination(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")
    path.mkdir(parents=True)


def copy_real_tree(source: Path, destination: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"source must be a real directory: {source}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"payload contains a symbolic link: {path}")
    shutil.copytree(source, destination, dirs_exist_ok=True)


def assemble_android(arguments: argparse.Namespace) -> None:
    clean_destination(arguments.ass_output)
    clean_destination(arguments.ffmpeg_output)
    for abi, source in (("arm64-v8a", arguments.arm64), ("armeabi-v7a", arguments.armv7)):
        copy_real_tree(source / "ass-runtime", arguments.ass_output / "jni" / abi)
        copy_real_tree(source / "ffmpeg-runtime", arguments.ffmpeg_output / "jni" / abi)
        manifests = (
            (arguments.ass_output, "ass-runtime.properties"),
            (arguments.ffmpeg_output, "runtime.properties"),
        )
        for destination_root, name in manifests:
            manifest = source / name
            if not manifest.is_file():
                raise ValueError(f"{abi} {name} is missing")
            destination = destination_root / "manifests" / abi
            destination.mkdir(parents=True)
            shutil.copyfile(manifest, destination / name)
    for output in (arguments.ass_output, arguments.ffmpeg_output):
        actual = {path.name for path in (output / "jni").iterdir()}
        if actual != {"arm64-v8a", "armeabi-v7a"}:
            raise ValueError("Android assembler produced an invalid ABI set")


def assemble_desktop(arguments: argparse.Namespace) -> None:
    clean_destination(arguments.ass_output)
    clean_destination(arguments.ffmpeg_output)
    sources = dict(item.split("=", 1) for item in arguments.target)
    if set(sources) != set(DESKTOP):
        raise ValueError("desktop assembler requires the exact four-target matrix")
    for target in DESKTOP:
        source = Path(sources[target]).resolve()
        ass_root = arguments.ass_output / "resources/META-INF/kmediaass/native" / target
        copy_real_tree(source / "ass-runtime", ass_root / "lib")
        shutil.copyfile(
            source / "ass-runtime.properties", ass_root / "ass-runtime.properties")
        ffmpeg_root = arguments.ffmpeg_output / "resources/META-INF/kmediaffmpeg/native" / target
        copy_real_tree(source / "ffmpeg-runtime", ffmpeg_root / "lib")
        shutil.copyfile(source / "runtime.properties", ffmpeg_root / "runtime.properties")


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def assemble_apple(arguments: argparse.Namespace) -> None:
    for output, names, manifest_name in (
        (arguments.ass_output, APPLE_ASS_FRAMEWORKS, "ass-runtime.properties"),
        (arguments.ffmpeg_output, APPLE_FFMPEG_FRAMEWORKS, "runtime.properties"),
    ):
        clean_destination(output)
        frameworks = output / "Frameworks"
        frameworks.mkdir()
        for name in names:
            device = arguments.device / "Frameworks" / f"{name}.framework"
            simulator = arguments.simulator / "Frameworks" / f"{name}.framework"
            if not device.is_dir() or not simulator.is_dir():
                raise ValueError(f"Apple framework slices are incomplete for {name}")
            run(
                "xcodebuild", "-create-xcframework",
                "-framework", str(device), "-framework", str(simulator),
                "-output", str(frameworks / f"{name}.xcframework"),
            )
        manifest = {
            "schemaVersion": 1,
            "frameworks": list(names),
            "targets": ["ios-arm64", "ios-simulator-arm64"],
            "version": arguments.version,
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        shutil.copyfile(
            arguments.device / manifest_name,
            output / f"{manifest_name.removesuffix('.properties')}-ios-arm64.properties",
        )
        shutil.copyfile(
            arguments.simulator / manifest_name,
            output / f"{manifest_name.removesuffix('.properties')}-ios-simulator-arm64.properties",
        )
        shutil.copyfile(ROOT / "LICENSE", output / "LICENSE")
        shutil.copyfile(ROOT / "NOTICE", output / "NOTICE")
        shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", output / "THIRD_PARTY_NOTICES.md")
        shutil.copyfile(ROOT / "docs/RELINKING.md", output / "RELINKING.md")
    ass_podspec = f"""Pod::Spec.new do |spec|
  spec.name                 = 'KMediaAssRuntime'
  spec.version              = '{arguments.version}'
  spec.summary              = 'Shared audited libass text runtime for KMedia projects.'
  spec.homepage             = 'https://github.com/SuvioMedia/KMediaFfmpegRuntime'
  spec.license              = {{ :type => 'LGPL-2.1-or-later', :file => 'LICENSE' }}
  spec.author               = {{ 'Shusek' => 'Shusek' }}
  spec.platform             = :ios, '16.2'
  spec.source               = {{ :http => 'https://github.com/SuvioMedia/KMediaFfmpegRuntime/releases/download/v{arguments.version}/kmedia-ass-runtime-{arguments.version}-apple-xcframeworks.zip', :sha256 => '__ARCHIVE_SHA256__' }}
  spec.vendored_frameworks  = 'Frameworks/*.xcframework'
end
"""
    ffmpeg_podspec = f"""Pod::Spec.new do |spec|
  spec.name                 = 'KMediaFfmpegRuntime'
  spec.version              = '{arguments.version}'
  spec.summary              = 'Shared audited FFmpeg runtime for KMedia projects.'
  spec.homepage             = 'https://github.com/SuvioMedia/KMediaFfmpegRuntime'
  spec.license              = {{ :type => 'LGPL-2.1-or-later', :file => 'LICENSE' }}
  spec.author               = {{ 'Shusek' => 'Shusek' }}
  spec.platform             = :ios, '16.2'
  spec.source               = {{ :http => 'https://github.com/SuvioMedia/KMediaFfmpegRuntime/releases/download/v{arguments.version}/kmedia-ffmpeg-runtime-{arguments.version}-apple-xcframeworks.zip', :sha256 => '__ARCHIVE_SHA256__' }}
  spec.dependency           'KMediaAssRuntime', '= {arguments.version}'
  spec.vendored_frameworks  = 'Frameworks/*.xcframework'
end
"""
    arguments.ass_podspec.write_text(ass_podspec)
    arguments.ffmpeg_podspec.write_text(ffmpeg_podspec)


def deterministic_zip(source: Path, destination: Path, epoch: int) -> None:
    date = tuple(__import__("time").gmtime(max(epoch, 315532800))[:6])
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, date_time=date)
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())


def package_apple(arguments: argparse.Namespace) -> None:
    deterministic_zip(arguments.source, arguments.archive, arguments.epoch)
    digest = hashlib.sha256(arguments.archive.read_bytes()).hexdigest()
    if arguments.podspec.exists():
        text = arguments.podspec.read_text()
        arguments.podspec.write_text(text.replace("__ARCHIVE_SHA256__", digest))


def corresponding_source(arguments: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="kmediaffmpeg-source-") as value:
        root = Path(value) / f"kmedia-ffmpeg-runtime-{arguments.version}-corresponding-source"
        root.mkdir()
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=arguments.repository, check=True, stdout=subprocess.PIPE,
        ).stdout.split(b"\0")
        for raw in tracked:
            if not raw:
                continue
            relative = Path(os.fsdecode(raw))
            source = arguments.repository / relative
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"unsupported tracked source entry: {relative}")
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        source_archives = root / "upstream-source"
        source_archives.mkdir()
        for path in sorted(arguments.evidence.glob("*.tar.*")):
            shutil.copyfile(path, source_archives / path.name)
        with tarfile.open(arguments.output, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(root.rglob("*")):
                info = archive.gettarinfo(str(path), arcname=path.relative_to(root.parent).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = arguments.epoch
                if path.is_file():
                    with path.open("rb") as source:
                        archive.addfile(info, source)
                else:
                    archive.addfile(info)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    android = commands.add_parser("android")
    android.add_argument("--arm64", type=Path, required=True)
    android.add_argument("--armv7", type=Path, required=True)
    android.add_argument("--ass-output", type=Path, required=True)
    android.add_argument("--ffmpeg-output", type=Path, required=True)
    android.set_defaults(function=assemble_android)
    desktop = commands.add_parser("desktop")
    desktop.add_argument("--target", action="append", required=True)
    desktop.add_argument("--ass-output", type=Path, required=True)
    desktop.add_argument("--ffmpeg-output", type=Path, required=True)
    desktop.set_defaults(function=assemble_desktop)
    apple = commands.add_parser("apple")
    apple.add_argument("--device", type=Path, required=True)
    apple.add_argument("--simulator", type=Path, required=True)
    apple.add_argument("--ass-output", type=Path, required=True)
    apple.add_argument("--ffmpeg-output", type=Path, required=True)
    apple.add_argument("--ass-podspec", type=Path, required=True)
    apple.add_argument("--ffmpeg-podspec", type=Path, required=True)
    apple.add_argument("--version", required=True)
    apple.set_defaults(function=assemble_apple)
    package = commands.add_parser("package-apple")
    package.add_argument("--source", type=Path, required=True)
    package.add_argument("--archive", type=Path, required=True)
    package.add_argument("--podspec", type=Path, required=True)
    package.add_argument("--epoch", type=int, required=True)
    package.set_defaults(function=package_apple)
    source = commands.add_parser("source")
    source.add_argument("--repository", type=Path, required=True)
    source.add_argument("--evidence", type=Path, required=True)
    source.add_argument("--output", type=Path, required=True)
    source.add_argument("--version", required=True)
    source.add_argument("--epoch", type=int, required=True)
    source.set_defaults(function=corresponding_source)
    arguments = parser.parse_args()
    arguments.function(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
