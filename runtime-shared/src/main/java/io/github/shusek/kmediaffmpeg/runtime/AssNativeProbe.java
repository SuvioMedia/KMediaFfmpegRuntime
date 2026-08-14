// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

final class AssNativeProbe {
    private AssNativeProbe() {}

    static native String runtimeId();
    static native String configurationSha256();
    static native int libassVersion();
}
