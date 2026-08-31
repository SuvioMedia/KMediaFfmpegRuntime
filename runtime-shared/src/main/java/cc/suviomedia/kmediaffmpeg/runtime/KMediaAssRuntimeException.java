// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

/** Fail-closed ASS runtime selection, verification, or loading error. */
public class KMediaAssRuntimeException extends IllegalStateException {
    public KMediaAssRuntimeException(String message) {
        super(message);
    }

    public KMediaAssRuntimeException(String message, Throwable cause) {
        super(message, cause);
    }
}
