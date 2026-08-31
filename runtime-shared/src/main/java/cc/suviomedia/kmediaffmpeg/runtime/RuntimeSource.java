// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

import java.io.File;
import java.io.IOException;
import java.util.Objects;

/** Selects the process-wide native runtime. No implementation downloads code. */
public abstract class RuntimeSource {
    private RuntimeSource() {}

    public static RuntimeSource bundled() {
        return Bundled.INSTANCE;
    }

    public static RuntimeSource externalDirectory(File directory) {
        return new ExternalDirectory(directory);
    }

    public static final class Bundled extends RuntimeSource {
        private static final Bundled INSTANCE = new Bundled();

        private Bundled() {}

        @Override
        public boolean equals(Object other) {
            return other instanceof Bundled;
        }

        @Override
        public int hashCode() {
            return 1;
        }

        @Override
        public String toString() {
            return "RuntimeSource.Bundled";
        }
    }

    public static final class ExternalDirectory extends RuntimeSource {
        private final File directory;

        private ExternalDirectory(File directory) {
            Objects.requireNonNull(directory, "directory");
            try {
                this.directory = directory.getCanonicalFile();
            } catch (IOException error) {
                throw new IllegalArgumentException("The external runtime directory is not canonical.", error);
            }
            if (!this.directory.isAbsolute()) {
                throw new IllegalArgumentException("The external runtime directory must be absolute.");
            }
        }

        public File directory() {
            return directory;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof ExternalDirectory
                    && directory.equals(((ExternalDirectory) other).directory);
        }

        @Override
        public int hashCode() {
            return directory.hashCode();
        }

        @Override
        public String toString() {
            return "RuntimeSource.ExternalDirectory(<redacted>)";
        }
    }
}
