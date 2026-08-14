// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

final class NativeProbe {
    private NativeProbe() {}

    static native String runtimeId();
    static native String configurationSha256();
    static native String ffmpegVersion();
    static native String ffmpegLicense();
}
