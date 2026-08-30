// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

final class AssNativeProbe {
    private AssNativeProbe() {}

    static native String runtimeId();
    static native String configurationSha256();
    static native int libassVersion();
}
