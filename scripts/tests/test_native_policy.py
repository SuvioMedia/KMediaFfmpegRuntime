# SPDX-License-Identifier: LGPL-2.1-or-later

import importlib.util
import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path, PurePosixPath
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("native_build", ROOT / "native/build.py")
BUILD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BUILD)
VERIFY_SPEC = importlib.util.spec_from_file_location(
    "verify_native_output", ROOT / "scripts/verify_native_output.py"
)
VERIFY = importlib.util.module_from_spec(VERIFY_SPEC)
assert VERIFY_SPEC.loader is not None
VERIFY_SPEC.loader.exec_module(VERIFY)


class NativePolicyTest(unittest.TestCase):
    def test_download_retries_transient_network_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.tar.xz"
            with (
                mock.patch.object(
                    BUILD.urllib.request,
                    "urlopen",
                    side_effect=[urllib.error.URLError("reset"), io.BytesIO(b"archive")],
                ) as open_url,
                mock.patch.object(BUILD.time, "sleep") as sleep,
            ):
                BUILD.download("https://example.invalid/source.tar.xz", destination)

            self.assertEqual(b"archive", destination.read_bytes())
            self.assertEqual(2, open_url.call_count)
            sleep.assert_called_once_with(1)

    def test_download_does_not_retry_non_transient_http_error(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.tar.xz"
            error = urllib.error.HTTPError(
                "https://example.invalid/source.tar.xz", 404, "Not Found", {}, None
            )
            with (
                mock.patch.object(BUILD.urllib.request, "urlopen", side_effect=error) as open_url,
                mock.patch.object(BUILD.time, "sleep") as sleep,
                self.assertRaises(urllib.error.HTTPError),
            ):
                BUILD.download("https://example.invalid/source.tar.xz", destination)

            open_url.assert_called_once()
            sleep.assert_not_called()

    def test_freetype_uses_its_official_sourceforge_release_mirror(self):
        freetype = BUILD.load_json(ROOT / "compliance/components/freetype.json")
        self.assertEqual(
            "https://downloads.sourceforge.net/project/freetype/freetype2/"
            "2.14.1/freetype-2.14.1.tar.xz",
            freetype["sourceUrl"],
        )

    def test_target_matrix_is_closed(self):
        policy = BUILD.load_json(ROOT / "compliance/policy/release-policy.json")
        self.assertEqual(
            set(policy["targets"]),
            {
                "android-arm64-v8a", "android-armeabi-v7a", "linux-x86_64", "linux-aarch64",
                "windows-x86_64", "macos-aarch64", "ios-arm64", "ios-simulator-arm64",
            },
        )

    def test_android_union_enables_mediacodec(self):
        arguments = BUILD.ffmpeg_arguments("android-arm64-v8a")
        self.assertIn("--enable-network", arguments)
        self.assertIn("--enable-openssl", arguments)
        self.assertIn("--enable-mediacodec", arguments)
        self.assertIn("--enable-encoder=h264_mediacodec", arguments)
        self.assertNotIn("--enable-gpl", arguments)
        self.assertIn("--disable-version3", arguments)

    def test_macos_union_enables_subtitles_and_videotoolbox(self):
        arguments = BUILD.ffmpeg_arguments("macos-aarch64")
        self.assertIn("--enable-network", arguments)
        self.assertIn("--enable-securetransport", arguments)
        self.assertNotIn("--enable-openssl", arguments)
        self.assertIn("--enable-libass", arguments)
        self.assertIn("--enable-filter=buffer,buffersink,subtitles,scale,format", arguments)
        self.assertIn("--enable-videotoolbox", arguments)
        self.assertIn(
            "--enable-hwaccel="
            "av1_videotoolbox,h264_videotoolbox,hevc_videotoolbox,"
            "mpeg2_videotoolbox,mpeg4_videotoolbox,vp9_videotoolbox",
            arguments,
        )
        self.assertIn("--enable-encoder=aac,h264_videotoolbox", arguments)

    def test_windows_union_enables_full_sdr_bridge_with_media_foundation(self):
        arguments = BUILD.ffmpeg_arguments("windows-x86_64")
        self.assertIn("--enable-network", arguments)
        self.assertIn("--enable-schannel", arguments)
        self.assertIn("--enable-libass", arguments)
        self.assertIn("--enable-filter=buffer,buffersink,subtitles,scale,format", arguments)
        self.assertIn("--enable-d3d11va", arguments)
        self.assertIn("--enable-mediafoundation", arguments)
        self.assertIn("--enable-encoder=aac,h264_mf", arguments)
        self.assertNotIn("--disable-network", arguments)
        self.assertEqual(
            {
                "networkInput": True,
                "httpsInput": True,
                "hdrToSdrToneMap": True,
                "subtitleBurnIn": True,
                "avcAacTranscode": True,
            },
            BUILD.ffmpeg_runtime_features("windows-x86_64"),
        )

    def test_network_profile_is_https_capable_on_every_target(self):
        protocol_argument = "--enable-protocol=crypto,file,http,https,httpproxy,pipe,tcp,tls"
        for target in BUILD.load_json(
            ROOT / "compliance/policy/release-policy.json"
        )["targets"]:
            with self.subTest(target=target):
                arguments = BUILD.ffmpeg_arguments(target)
                self.assertIn("--enable-network", arguments)
                self.assertIn(protocol_argument, arguments)
                self.assertNotIn("--disable-network", arguments)

    def test_openssl_targets_do_not_need_the_legacy_dtls_patch(self):
        ffmpeg = BUILD.load_json(ROOT / "compliance/components/ffmpeg.json")
        protocol_argument = next(
            value for value in ffmpeg["buildArguments"]
            if value.startswith("--enable-protocol=")
        )
        self.assertNotIn("udp", protocol_argument.split("=", 1)[1].split(","))
        self.assertNotIn("platformPatches", ffmpeg)

    def test_verifier_rejects_undefined_private_ffmpeg_symbols(self):
        symbol_table = """
   364: 00000000 0 NOTYPE GLOBAL DEFAULT UND ff_udp_get_last_recv_addr
   365: 00000000 0 FUNC GLOBAL DEFAULT UND avpriv_packet_list_get@LIBAVCODEC_63
"""
        with (
            mock.patch.object(VERIFY, "run", return_value=symbol_table),
            self.assertRaisesRegex(ValueError, "ff_udp_get_last_recv_addr"),
        ):
            VERIFY.verify_no_undefined_ffmpeg_internal_symbols(
                Path("libkmediaffmpeg_avformat.so"), "android-armeabi-v7a", "readelf"
            )

    def test_dynamic_symbol_parser_separates_strong_imports_from_weak_ones(self):
        symbol_table = """
Symbol table '.dynsym' contains 4 entries:
   Num:    Value  Size Type    Bind   Vis      Ndx Name
     1: 00000000     0 FUNC    GLOBAL DEFAULT  UND memcpy@LIBC
     2: 00000000     0 FUNC    WEAK   DEFAULT  UND getentropy
     3: 00001000    24 FUNC    GLOBAL DEFAULT   12 av_version_info@@LIBAVUTIL_61
"""
        with mock.patch.object(VERIFY, "run", return_value=symbol_table):
            defined, undefined = VERIFY.dynamic_symbols(Path("runtime.so"), "readelf")
        self.assertEqual({"av_version_info"}, defined)
        self.assertEqual({"memcpy"}, undefined)

    def test_linux_uses_pinned_openssl(self):
        arguments = BUILD.ffmpeg_arguments("linux-x86_64")
        self.assertIn("--enable-openssl", arguments)
        component = BUILD.load_json(ROOT / "compliance/components/openssl.json")
        self.assertEqual("3.5.7", component["version"])
        self.assertEqual("Apache-2.0", component["builtOutputLicenseSpdx"])

    def test_ios_uses_platform_tls(self):
        arguments = BUILD.ffmpeg_arguments("ios-arm64")
        self.assertIn("--enable-securetransport", arguments)
        self.assertNotIn("--enable-openssl", arguments)

    def test_windows_runtime_manifest_authenticates_full_bridge_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            library = "kmediaffmpeg_avcodec-kmb-63.dll"
            (runtime / library).write_bytes(b"runtime")
            manifest = root / "runtime.properties"

            BUILD.write_manifest(
                manifest,
                "windows-x86_64",
                "0.1.0-test",
                "runtime-id",
                "configuration",
                runtime,
                [library],
                ("ffmpeg",),
                "ass-runtime-id",
            )

            properties = dict(
                line.split("=", 1)
                for line in manifest.read_text().splitlines()
            )
            self.assertEqual("true", properties["feature.hdrToSdrToneMap"])
            self.assertEqual("true", properties["feature.subtitleBurnIn"])
            self.assertEqual("true", properties["feature.avcAacTranscode"])
            self.assertEqual("true", properties["feature.networkInput"])
            self.assertEqual("true", properties["feature.httpsInput"])

    def test_shared_profile_contains_legacy_avi_asf_video_and_audio_decoders(self):
        arguments = BUILD.ffmpeg_arguments("linux-x86_64")
        demuxers = next(value for value in arguments if value.startswith("--enable-demuxer="))
        decoders = next(value for value in arguments if value.startswith("--enable-decoder="))
        parsers = next(value for value in arguments if value.startswith("--enable-parser="))

        self.assertIn("avi", demuxers)
        self.assertIn("asf", demuxers)
        for decoder in ("mjpeg", "vc1", "wmapro", "wmav2", "wmv3"):
            self.assertIn(decoder, decoders)
        self.assertIn("vc1", parsers)

    def test_shared_profile_contains_cast_hls_output_muxers(self):
        arguments = BUILD.ffmpeg_arguments("macos-aarch64")
        muxers = next(value for value in arguments if value.startswith("--enable-muxer="))
        enabled = set(muxers.split("=", 1)[1].split(","))

        self.assertEqual({"hls", "mp4", "mpegts"}, enabled)

    @unittest.skipIf(os.name == "nt", "Creating symlinks requires elevated Windows privileges")
    def test_macos_rewrites_major_version_install_names_to_rpath(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix"
            runtime = root / "runtime"
            library = prefix / "lib"
            library.mkdir(parents=True)
            avutil = library / "libkmediaffmpeg_avutil.61.1.101.dylib"
            avutil.write_bytes(b"avutil")
            (library / "libkmediaffmpeg_avutil.61.dylib").symlink_to(avutil.name)
            swresample = library / "libkmediaffmpeg_swresample.7.1.101.dylib"
            swresample.write_bytes(b"swresample")
            absolute_dependency = str(library / "libkmediaffmpeg_avutil.61.dylib")

            def command(*arguments: str, **_kwargs: object) -> str:
                if arguments[:2] == ("otool", "-L"):
                    if "swresample" in arguments[2]:
                        return f"{arguments[2]}:\n\t{absolute_dependency} (compatibility version 60.0.0)\n"
                    return f"{arguments[2]}:\n"
                return ""

            with (
                mock.patch.object(BUILD, "LOGICAL_LIBRARIES", ("avutil", "swresample")),
                mock.patch.object(BUILD, "run", side_effect=command) as invoke,
            ):
                BUILD.copy_and_rewrite_runtime(prefix, runtime, "macos-aarch64")

            self.assertIn(
                mock.call(
                    "install_name_tool", "-change", absolute_dependency,
                    "@rpath/libkmediaffmpeg_avutil.dylib",
                    str(runtime / "libkmediaffmpeg_swresample.dylib"),
                ),
                invoke.call_args_list,
            )

    def test_runtime_identity_is_release_wide_and_configuration_is_target_specific(self):
        android = BUILD.configuration_identity("android-arm64-v8a", BUILD.ffmpeg_arguments("android-arm64-v8a"))
        again = BUILD.configuration_identity("android-arm64-v8a", BUILD.ffmpeg_arguments("android-arm64-v8a"))
        linux = BUILD.configuration_identity("linux-x86_64", BUILD.ffmpeg_arguments("linux-x86_64"))
        self.assertEqual(android, again)
        self.assertEqual(android[0], linux[0])
        self.assertNotEqual(android[1], linux[1])

    def test_ass_runtime_identity_is_release_wide_and_configuration_is_target_specific(self):
        android = BUILD.ass_configuration_identity("android-arm64-v8a")
        linux = BUILD.ass_configuration_identity("linux-x86_64")
        self.assertEqual(android[0], linux[0])
        self.assertNotEqual(android[1], linux[1])

    def test_runtime_id_is_always_ascii_lf(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "runtime-id.txt"
            BUILD.write_runtime_id(output, "runtime-id")
            self.assertEqual(b"runtime-id\n", output.read_bytes())

    def test_command_path_converts_windows_paths_for_msys_tools(self):
        with (
            mock.patch.object(BUILD.platform, "system", return_value="Windows"),
            mock.patch.object(BUILD, "run", return_value="/d/a/_temp/work\n") as invoke,
        ):
            self.assertEqual("/d/a/_temp/work", BUILD.command_path(Path("D:/a/_temp/work")))
        invoke.assert_called_once_with("cygpath", "-u", str(Path("D:/a/_temp/work")))

    def test_command_path_keeps_posix_paths(self):
        with mock.patch.object(BUILD.platform, "system", return_value="Darwin"):
            self.assertEqual("/tmp/work", BUILD.command_path(PurePosixPath("/tmp/work")))

    def test_find_library_ignores_windows_definition_file(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            (prefix / "bin").mkdir()
            (prefix / "lib").mkdir()
            runtime = prefix / "bin/libkmediaffmpeg_avutil-61.dll"
            runtime.touch()
            (prefix / "lib/libkmediaffmpeg_avutil-61.def").touch()

            self.assertEqual(runtime, BUILD.find_library(prefix, "avutil", "windows-x86_64"))

    def test_release_build_exports_setup_java_home_into_msys(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("id: setup_java", workflow)
        self.assertIn("JAVA_HOME: ${{ steps.setup_java.outputs.path }}", workflow)
        self.assertIn("| tr -d '\\r' | sort -u", workflow)

    def test_rc_release_requires_both_android_abi_symbol_closure_jobs(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        build = (ROOT / "native/build.py").read_text()
        verifier = (ROOT / "scripts/verify_native_output.py").read_text()

        self.assertNotIn("android_armv7_native_graph_verified", workflow)
        self.assertIn("android-arm64-v8a", workflow)
        self.assertIn("android-armeabi-v7a", workflow)
        self.assertIn("needs: [readiness, native, apple]", workflow)
        self.assertIn('--arm64 "$RUNNER_TEMP/native/native-android-arm64-v8a"', workflow)
        self.assertIn('--armv7 "$RUNNER_TEMP/native/native-android-armeabi-v7a"', workflow)
        self.assertIn('if [[ "$RELEASE_VERSION" != *-rc.* ]]; then', workflow)
        self.assertIn('test "$ARM_MATRIX" = true', workflow)
        self.assertIn('verification.extend(["--readelf", tools["readelf"]])', build)
        self.assertIn("verify_android_symbol_closure(", verifier)

    def test_release_packages_ass_frameworks_only_in_ios_sdk_archives(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        sdk_packaging = workflow.split(
            "      - name: Package every public SDK with its ABI manifest and evidence",
            maxsplit=1,
        )[1].split(
            "      - name: Stage all four public Maven coordinates",
            maxsplit=1,
        )[0]
        non_apple_sdks, apple_sdks = sdk_packaging.split(
            "          for target in ios-arm64 ios-simulator-arm64; do",
            maxsplit=1,
        )
        non_apple_ass_archive = non_apple_sdks.rsplit(
            '              "$RUNNER_TEMP/kmedia-ass-runtime-$RELEASE_VERSION-$target-sdk.tar.gz"',
            maxsplit=1,
        )[1]
        self.assertIn('-C "$source/ass" sdk \\', non_apple_ass_archive)
        self.assertNotIn('-C "$source/ass" sdk Frameworks \\', non_apple_ass_archive)
        self.assertIn('-C "$source/ass" sdk Frameworks \\', apple_sdks)

    def test_desktop_java_home_uses_explicit_path_when_msys_hides_javac(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.object(BUILD.platform, "system", return_value="Windows"),
                mock.patch.object(BUILD.shutil, "which", return_value=None),
                mock.patch.dict(BUILD.os.environ, {"JAVA_HOME": directory}),
            ):
                self.assertEqual(Path(directory), BUILD.desktop_java_home())

    def test_windows_probe_links_against_import_library_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            prefix = root / "prefix"
            work = root / "work"
            java = root / "java"
            runtime.mkdir()
            (prefix / "include").mkdir(parents=True)
            (prefix / "lib").mkdir()
            avutil_import = prefix / "lib/libkmediaffmpeg_avutil-61.def"
            ass_import = prefix / "lib/libkmediaffmpeg_ass.dll.a"
            avutil_import.touch()
            ass_import.touch()
            work.mkdir()
            (java / "include/win32").mkdir(parents=True)
            with (
                mock.patch.object(BUILD.platform, "system", return_value="Windows"),
                mock.patch.dict(BUILD.os.environ, {"JAVA_HOME": str(java)}),
                mock.patch.object(BUILD, "run") as invoke,
            ):
                BUILD.compile_probe(
                    "windows-x86_64", runtime, prefix, work, "runtime-id", "configuration",
                    None, None, None,
                )
            command = invoke.call_args.args
            self.assertIn(str(avutil_import), command)
            self.assertNotIn(str(ass_import), command)
            self.assertNotIn("-L", command)

    def test_windows_ass_probe_links_only_against_ass_import_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            prefix = root / "prefix"
            work = root / "work"
            java = root / "java"
            runtime.mkdir()
            (prefix / "include").mkdir(parents=True)
            (prefix / "lib").mkdir()
            ass_import = prefix / "lib/libkmediaffmpeg_ass.dll.a"
            ass_import.touch()
            work.mkdir()
            (java / "include/win32").mkdir(parents=True)
            with (
                mock.patch.object(BUILD.platform, "system", return_value="Windows"),
                mock.patch.dict(BUILD.os.environ, {"JAVA_HOME": str(java)}),
                mock.patch.object(BUILD, "run") as invoke,
            ):
                BUILD.compile_ass_probe(
                    "windows-x86_64", runtime, prefix, work, "runtime-id", "configuration",
                    None, None, None,
                )
            command = invoke.call_args.args
            self.assertIn(str(ass_import), command)
            self.assertNotIn("-L", command)

    def test_windows_ass_build_does_not_import_msys_toolchain_runtimes(self):
        self.assertIn(
            "--extra-ldflags=-no-pthread -static-libgcc",
            BUILD.ffmpeg_arguments("windows-x86_64"),
        )
        self.assertIn(
            "-Dc_link_args=-static-libgcc",
            BUILD.component_arguments("harfbuzz", "windows-x86_64"),
        )
        libass = BUILD.load_json(ROOT / "compliance/components/libass.json")
        patch_policy = libass["platformPatches"]["windows"][0]
        self.assertEqual(
            "native/patches/libass-0.17.5-disable-iconv-on-windows.patch",
            patch_policy["path"],
        )
        patch = ROOT / patch_policy["path"]
        self.assertEqual(patch_policy["sha256"], BUILD.sha256(patch))
        self.assertIn("if host_system != 'windows'", patch.read_text())

    def test_windows_workflows_test_with_only_os_dll_search_paths(self):
        system_path = '$systemPath = "$env:SystemRoot\\System32;$env:SystemRoot"'
        probe_path = '$env:Path = "$(Join-Path $runtime \'lib\');$systemPath"'
        clean_test_path = '$env:Path = $systemPath'
        for workflow in ("ci.yml", "release.yml"):
            text = (ROOT / ".github/workflows" / workflow).read_text()
            self.assertIn(system_path, text)
            self.assertIn(probe_path, text)
            self.assertIn(clean_test_path, text)
            self.assertLess(text.index(probe_path), text.index(clean_test_path))
            self.assertIn("-PkmediaAssTestRuntime=$runtime", text)
            self.assertIn("-PkmediaFfmpegTestRuntime=$runtime", text)

    def test_native_workflows_reuse_one_hash_verified_source_inventory(self):
        fetcher = (ROOT / "scripts/fetch_sources.py").read_text()
        self.assertIn("build.sha256(destination)", fetcher)
        for workflow in ("ci.yml", "release.yml"):
            text = (ROOT / ".github/workflows" / workflow).read_text()
            self.assertIn("scripts/fetch_sources.py", text)
            self.assertIn("name: pinned-native-sources", text)
            self.assertIn("--source-archives", text)


if __name__ == "__main__":
    unittest.main()
