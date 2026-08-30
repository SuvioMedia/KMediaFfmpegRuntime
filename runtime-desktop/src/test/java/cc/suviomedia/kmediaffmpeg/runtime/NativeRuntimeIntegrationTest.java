// SPDX-License-Identifier: LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.io.File;
import java.nio.file.Files;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

final class NativeRuntimeIntegrationTest {
    @Test
    void loadsAndReusesTheExactExternalGraph() throws Exception {
        String configured = System.getProperty("kmediaFfmpegTestRuntime");
        boolean bundled = Boolean.getBoolean("kmediaFfmpegTestBundled");
        Assumptions.assumeTrue(bundled || (configured != null && !configured.isBlank()));
        RuntimeSource source = bundled
                ? RuntimeSource.bundled()
                : RuntimeSource.externalDirectory(new File(configured));
        RuntimeReport first = KMediaFfmpegRuntime.initialize(source);
        RuntimeReport second = KMediaFfmpegRuntime.initialize(source);
        assertSame(first, second);
        assertEquals("9.0.1", first.componentVersions().get("ffmpeg"));
        assertEquals("0.17.5", first.componentVersions().get("libass"));
        assertEquals(first, KMediaFfmpegRuntime.current().orElseThrow());
        assertEquals(
                KMediaAssRuntime.loadedLibraryDirectory(),
                KMediaFfmpegRuntime.loadedLibraryDirectory());
        try (var files = Files.list(KMediaFfmpegRuntime.loadedLibraryDirectory())) {
            assertEquals(12L, files.filter(Files::isRegularFile).count());
        }
    }
}
