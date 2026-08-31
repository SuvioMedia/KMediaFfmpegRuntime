<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->

# Android ARM release gates

Every RC and stable release builds both `arm64-v8a` and `armeabi-v7a` from the
same pinned source inventory in hosted Actions. `native/build.py` runs the native
output verifier for each ABI before its artifact can reach the aggregate and
publication jobs.

For Android ELF payloads, the verifier resolves every strong dynamic import
against the packaged shared graph and the NDK API 23 platform stubs. It also
rejects unresolved private FFmpeg `ff_*` symbols. The aggregate job requires both
ABI artifacts and assembles them into one hash-bound Android payload. This is the
automatic RC gate; it does not depend on an emulator, Rosetta, or a manual ARMv7
attestation.

The static RC gate proves ABI, API-level, and loader-symbol closure. It does not
claim Android framework, MediaCodec, rendering, or playback execution.

## Stable hardware gate

Before dispatching a stable release, run the consumer test app on native ARM
hardware with the exact candidate commit and runtime ID.

The required matrix is:

- arm64-v8a, API 28 and API 35;
- armeabi-v7a, API 28 on an ARM emulator or physical device;
- MediaCodec-copy success, forced MediaCodec failure, and software fallback;
- H.264, HEVC, VP9, AV1, 10-bit/HDR, ASS, seek, audio, and Surface recreation;
- MPV playback with ASS while KMediaBridge remux/tone-map remains active.

Export a path-free JSON report, hash the report with SHA-256, and retain it with
the release evidence. The release workflow requires the confirmation boolean,
tested 40-character commit, runtime ID, and report digest. It rejects a tested
commit other than the tagged release revision.

The release workflow accepts `android_arm_matrix_verified` only as the explicit
stable hardware attestation. RC releases remain blocked unless both hosted
Android native jobs and their symbol-closure verification pass. x86 and x86_64
are never alternatives for either ARM ABI.
