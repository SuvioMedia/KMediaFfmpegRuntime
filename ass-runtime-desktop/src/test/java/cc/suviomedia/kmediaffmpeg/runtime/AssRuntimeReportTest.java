// SPDX-License-Identifier: LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.File;
import java.util.Map;
import org.junit.jupiter.api.Test;

final class AssRuntimeReportTest {
    @Test
    void reportIsImmutableAndSourcePathIsRedacted() {
        RuntimeReport report =
                new RuntimeReport(
                        "kmediaass-test",
                        "linux",
                        "x86_64",
                        "0".repeat(64),
                        Map.of("libass", "0.17.5"),
                        Map.of("libass", "ISC"));
        assertEquals("0.17.5", report.componentVersions().get("libass"));
        assertThrows(
                UnsupportedOperationException.class,
                () -> report.componentVersions().put("x", "y"));
        assertEquals(
                "RuntimeSource.ExternalDirectory(<redacted>)",
                RuntimeSource.externalDirectory(new File(".").getAbsoluteFile()).toString());
    }
}
