// SPDX-License-Identifier: LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.File;
import java.util.Map;
import org.junit.jupiter.api.Test;

final class RuntimeReportTest {
    private static final Map<String, String> VERSIONS = Map.of(
            "ffmpeg", "9.0.1", "freetype", "2.14.1", "fribidi", "1.0.16",
            "harfbuzz", "12.2.0", "libass", "0.17.5");
    private static final Map<String, String> LICENSES = Map.of(
            "ffmpeg", "LGPL-2.1-or-later", "freetype", "FTL", "fribidi", "LGPL-2.1-or-later",
            "harfbuzz", "MIT", "libass", "ISC");

    @Test
    void reportIsImmutableAndPathFree() {
        RuntimeReport report = new RuntimeReport(
                "kmediaffmpeg-test", "linux", "x86_64", "0".repeat(64), VERSIONS, LICENSES);
        assertEquals("9.0.1", report.componentVersions().get("ffmpeg"));
        assertThrows(UnsupportedOperationException.class, () -> report.componentVersions().put("x", "y"));
    }

    @Test
    void externalSourceRedactsItsPath() {
        RuntimeSource source = RuntimeSource.externalDirectory(new File(".").getAbsoluteFile());
        assertEquals("RuntimeSource.ExternalDirectory(<redacted>)", source.toString());
    }

    @Test
    void rejectsDifferentVersionAndLicenseInventories() {
        assertThrows(IllegalArgumentException.class, () -> new RuntimeReport(
                "id", "linux", "x86_64", "0".repeat(64), VERSIONS, Map.of("ffmpeg", "LGPL-2.1-or-later")));
    }
}
