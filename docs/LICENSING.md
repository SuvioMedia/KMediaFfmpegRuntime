<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->

# Licensing

The project-authored Java loader and inspection classes listed in the root
`LICENSE` are dual-licensed under `MIT OR LGPL-2.1-or-later`. This includes the
corresponding project-authored source and bytecode first conveyed in
0.1.0-rc.7. A closed application may select MIT when GraalVM Native Image
compiles those classes into its executable.

Project-authored native probes, native build material, patches, compliance and
release tooling, and replacement/relinking material remain
LGPL-2.1-or-later. Each upstream component keeps its own license. Maven and
CocoaPods payloads are aggregates, not a claim that permissively licensed
components were relicensed.

The distribution boundary is explicit:

- `KMediaAssRuntime` contains libass, FreeType, FriBidi, HarfBuzz, and its
  identity probe;
- `KMediaFfmpegRuntime` contains only FFmpeg and its identity probe, and depends
  on the exact matching ASS runtime;
- KMediaPlayer, KMediaMpv, and KMediaBridge client code and adapters are
  independent artifacts under their own licenses.

FFmpeg is configured with `--disable-gpl`, `--disable-version3`,
`--disable-nonfree`, `--disable-static`, and `--enable-shared`. Release gates
inspect the compiled configuration and reject a mismatch.

Consuming a dynamically linked runtime does not relicense those client
artifacts. Distributors remain responsible for preserving notices, source
offers, replacement, relinking, and debugging rights required by the licenses
that apply to their distribution.

The MIT choice for the Java loader does not weaken those obligations for
FFmpeg, FriBidi, or another LGPL native library. Those libraries must remain
separate and replaceable, and their corresponding source and notices must still
be provided as required by their licenses.
