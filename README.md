<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->

# KMediaFfmpegRuntime

One audited native graph shared by KMediaPlayer, KMediaMpv, and KMediaBridge.
The graph is distributed as two composable runtimes:

- `KMediaAssRuntime`: libass 0.17.5, FreeType, FriBidi, and HarfBuzz;
- `KMediaFfmpegRuntime`: FFmpeg 8.1.2 and an exact dependency on
  `KMediaAssRuntime`.

This repository provides native distributions, loaders, inspection APIs, and
versioned SDKs. It is not a general-purpose Java binding for FFmpeg or libass.
GPL, version-3-only, nonfree, programs, static runtime libraries,
Android x86, and Intel macOS are excluded by closed policy.

The FFmpeg runtime enables direct HTTP/HTTPS input for MPV clients. Android and
Linux use a pinned OpenSSL 3.5 LTS build, Apple uses Secure Transport, and
Windows uses SChannel. Applications must supply a CA file when enabling peer
verification on Android and Linux.

## Published coordinates

```kotlin
dependencies {
    implementation("io.github.shusek:kmedia-ass-runtime-android:0.1.0-rc.7")
    implementation("io.github.shusek:kmedia-ass-runtime-desktop:0.1.0-rc.7")

    // Adds FFmpeg and pulls the exact ASS runtime transitively.
    implementation("io.github.shusek:kmedia-ffmpeg-runtime-android:0.1.0-rc.7")
    implementation("io.github.shusek:kmedia-ffmpeg-runtime-desktop:0.1.0-rc.7")
}
```

Normal KMediaPlayer applications do not add these coordinates directly. The
optional ASS, MPV, and KMediaBridge adapters bring the exact runtime
transitively. Depending on both MPV and KMediaBridge, or on either backend plus
`composemediaplayer-ass`, still resolves one copy of each text library.

On Android and JVM, `KMediaAssRuntime.initialize(RuntimeSource.bundled())`
loads and verifies the shared text stack. `KMediaFfmpegRuntime.initialize(...)`
first selects that exact ASS runtime, then loads FFmpeg. Both initializers are
process-wide and idempotent. Selecting a different runtime ID after
initialization fails before another native client can be loaded.

Apple consumers use the hash-bound `KMediaAssRuntime.podspec` and
`KMediaFfmpegRuntime.podspec` from the matching GitHub Release. The FFmpeg pod
depends on the exact ASS pod version. Both contain arm64 device and Apple
Silicon simulator XCFramework slices only.

## Artifact ownership

`kmedia-ass-runtime-*` owns exactly the four text libraries and the ASS identity
probe. `kmedia-ffmpeg-runtime-*` owns exactly the six FFmpeg libraries and the
FFmpeg identity probe. Client artifacts own neither set. The Maven dependency
graph and CocoaPods dependency keep the two scopes version-locked without
duplicating files.

## Targets

- Android `arm64-v8a` and `armeabi-v7a`, API 23+
- Linux x86_64 and aarch64
- Windows x86_64
- macOS arm64
- iOS arm64 device and arm64 simulator, iOS 16.2+

Each release also contains per-target SDKs, manifests, source archives, build
arguments, an SBOM, SHA-256 sums, and replacement instructions. See
[licensing](docs/LICENSING.md), [relinking](docs/RELINKING.md), and the
machine-readable policy under `compliance/` before redistribution.

The reviewed common profile includes local AVI and ASF/WMV demuxing together
with MPEG-4 Part 2, MJPEG, VC-1, WMV1/2/3 and WMA-family decoding. The macOS
profile additionally exposes the audited VideoToolbox decode path and AVC/AAC
encoding needed by native MPV output and the AVFoundation compatibility bridge.
The Windows profile exposes the matching libass filter graph, D3D11 context,
Media Foundation AVC encoder and AAC encoder needed by KMediaBridge to produce
Media Foundation-compatible fragmented MP4. SDK manifests authenticate these
optional desktop capabilities so older runtimes remain fail-closed.
