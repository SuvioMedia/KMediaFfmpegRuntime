// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

/** Fail-closed FFmpeg runtime selection, verification, or loading error. */
public final class KMediaFfmpegRuntimeException extends IllegalStateException {
    public KMediaFfmpegRuntimeException(String message) {
        super(message);
    }

    public KMediaFfmpegRuntimeException(String message, Throwable cause) {
        super(message, cause);
    }
}
