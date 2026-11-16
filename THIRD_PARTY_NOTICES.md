<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->

# Third-party notices

- FFmpeg 9.0.1: built as `LGPL-2.1-or-later`; GPL, version-3-only and nonfree
  components are disabled. <https://ffmpeg.org/>
- libass 0.17.5: ISC. <https://github.com/libass/libass>
- FreeType: FreeType Project License or GPL-2.0-or-later; this distribution
  uses the FreeType Project License option. <https://freetype.org/>
- FriBidi: LGPL-2.1-or-later. <https://github.com/fribidi/fribidi>
- HarfBuzz: MIT-style license. <https://github.com/harfbuzz/harfbuzz>
- nv-codec-headers (ffnvcodec) 12.1.14.1: MIT; see
  `LICENSES/MIT-nv-codec-headers.txt`. Only the Linux x86-64 FFmpeg build
  compiles these headers, for NVDEC decoding and NVENC encoding. No NVIDIA
  library is shipped or linked: FFmpeg loads `libcuda.so.1`, `libnvcuvid.so.1`
  and `libnvidia-encode.so.1` from the installed NVIDIA driver when a hardware
  decoder or encoder is opened. <https://github.com/FFmpeg/nv-codec-headers>
- OpenSSL 3.5.7 LTS: Apache-2.0. It is linked into the Android and Linux FFmpeg
  network transport; Apple uses Secure Transport and Windows uses SChannel.
  <https://github.com/openssl/openssl>

Exact source archives, hashes, detached signatures where supplied upstream,
build arguments and license files are included in every corresponding-source
release asset.
