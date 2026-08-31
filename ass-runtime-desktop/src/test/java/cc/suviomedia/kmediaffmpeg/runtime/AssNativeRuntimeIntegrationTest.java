// SPDX-License-Identifier: LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.io.File;
import java.nio.file.Files;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

final class AssNativeRuntimeIntegrationTest {
    @Test
    void loadsAndReusesTheExactExternalTextStack() throws Exception {
        String configured = System.getProperty("kmediaAssTestRuntime");
        boolean bundled = Boolean.getBoolean("kmediaAssTestBundled");
        Assumptions.assumeTrue(bundled || (configured != null && !configured.isBlank()));

        RuntimeSource source = bundled
                ? RuntimeSource.bundled()
                : RuntimeSource.externalDirectory(new File(configured));
        RuntimeReport first = KMediaAssRuntime.initialize(source);
        RuntimeReport second = KMediaAssRuntime.initialize(source);

        assertSame(first, second);
        assertEquals("0.17.5", first.componentVersions().get("libass"));
        assertSame(first, KMediaAssRuntime.current().orElseThrow());
        if (!bundled) {
            assertNotEquals(
                    new File(configured, "lib").getCanonicalFile().toPath(),
                    KMediaAssRuntime.loadedLibraryDirectory());
        }
        try (var files = Files.list(KMediaAssRuntime.loadedLibraryDirectory())) {
            assertEquals(5L, files.filter(Files::isRegularFile).count());
        }
    }
}
