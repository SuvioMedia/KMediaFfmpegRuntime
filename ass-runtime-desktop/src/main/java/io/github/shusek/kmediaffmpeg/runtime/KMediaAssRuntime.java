// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Optional;
import java.util.Set;

/** Process-wide loader and inspector for the shared desktop ASS text stack. */
public final class KMediaAssRuntime {
    private static final Object LOCK = new Object();
    private static RuntimeReport current;
    private static Path currentLibraryDirectory;
    private static KMediaAssRuntimeException terminalFailure;

    private KMediaAssRuntime() {}

    public static RuntimeReport initialize(RuntimeSource source) {
        if (source == null) {
            throw new NullPointerException("source");
        }
        synchronized (LOCK) {
            if (terminalFailure != null) {
                throw terminalFailure;
            }
            try {
                RuntimeCandidate candidate = source instanceof RuntimeSource.Bundled
                        ? inspectBundled()
                        : inspectExternal(((RuntimeSource.ExternalDirectory) source).directory());
                if (current != null) {
                    if (!current.runtimeId().equals(candidate.manifest.report.runtimeId())) {
                        throw new KMediaAssRuntimeException(
                                "A different KMediaAssRuntime is already initialized in this process.");
                    }
                    return current;
                }
                verifyPlatform(candidate.manifest.report);
                Path libraryDirectory = stageLibraries(candidate);
                for (String library : candidate.manifest.libraries) {
                    System.load(libraryDirectory.resolve(library).toAbsolutePath().toString());
                }
                verifyNativeIdentity(candidate.manifest.report);
                currentLibraryDirectory = libraryDirectory;
                current = candidate.manifest.report;
                return current;
            } catch (KMediaAssRuntimeException error) {
                if (current == null) {
                    terminalFailure = error;
                }
                throw error;
            } catch (Exception | LinkageError error) {
                terminalFailure =
                        new KMediaAssRuntimeException(
                                "The shared desktop ASS runtime could not be initialized.", error);
                throw terminalFailure;
            }
        }
    }

    public static Optional<RuntimeReport> current() {
        synchronized (LOCK) {
            return Optional.ofNullable(current);
        }
    }

    public static RuntimeReport currentOrNull() {
        synchronized (LOCK) {
            return current;
        }
    }

    static Path loadedLibraryDirectory() {
        synchronized (LOCK) {
            if (currentLibraryDirectory == null) {
                throw new IllegalStateException("KMediaAssRuntime is not initialized.");
            }
            return currentLibraryDirectory;
        }
    }

    private static RuntimeCandidate inspectExternal(File root) throws IOException {
        Path realRoot = root.toPath().toRealPath(LinkOption.NOFOLLOW_LINKS);
        if (!Files.isDirectory(realRoot, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("The external ASS runtime root is not a real directory.");
        }
        AssRuntimeManifest manifest;
        try (InputStream input = Files.newInputStream(realRoot.resolve("ass-runtime.properties"))) {
            manifest = AssRuntimeManifest.read(input);
        }
        Path libraryDirectory = realRoot.resolve("lib");
        validateLibraries(libraryDirectory, manifest);
        return new RuntimeCandidate(libraryDirectory, null, manifest);
    }

    private static RuntimeCandidate inspectBundled() throws IOException {
        String classifier = platformClassifier();
        String base = "/META-INF/kmediaass/native/" + classifier + "/";
        AssRuntimeManifest manifest;
        try (InputStream input = KMediaAssRuntime.class.getResourceAsStream(
                base + "ass-runtime.properties")) {
            if (input == null) {
                throw new IOException("No bundled ASS runtime exists for " + classifier + '.');
            }
            manifest = AssRuntimeManifest.read(input);
        }
        return new RuntimeCandidate(null, base, manifest);
    }

    private static Path stageLibraries(RuntimeCandidate candidate) throws IOException {
        Path root = Files.createTempDirectory("kmediaass-" + ProcessHandle.current().pid() + "-");
        tighten(root);
        Path libraries = Files.createDirectory(root.resolve("lib"));
        tighten(libraries);
        for (String library : candidate.manifest.libraries) {
            Path output = libraries.resolve(library);
            if (candidate.sourceLibraryDirectory != null) {
                Files.copy(candidate.sourceLibraryDirectory.resolve(library), output);
            } else {
                try (InputStream input =
                        KMediaAssRuntime.class.getResourceAsStream(
                                candidate.resourceBase + "lib/" + library)) {
                    if (input == null) {
                        throw new IOException(
                                "A bundled ASS native library is missing: " + library);
                    }
                    Files.copy(input, output);
                }
            }
        }
        validateLibraries(libraries, candidate.manifest);
        return libraries;
    }

    private static void validateLibraries(Path directory, AssRuntimeManifest manifest)
            throws IOException {
        Path realDirectory = directory.toRealPath(LinkOption.NOFOLLOW_LINKS);
        if (!Files.isDirectory(realDirectory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("The ASS runtime library directory is missing.");
        }
        for (String library : manifest.libraries) {
            Path file = realDirectory.resolve(library);
            if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(file)
                    || !sha256(file).equals(manifest.hashes.get(library))) {
                throw new IOException("An ASS runtime library failed verification.");
            }
        }
    }

    private static void verifyPlatform(RuntimeReport report) {
        String classifier = platformClassifier();
        String[] fields = classifier.split("-", 2);
        if (!report.platform().equals(fields[0]) || !report.abi().equals(fields[1])) {
            throw new KMediaAssRuntimeException(
                    "The ASS runtime manifest targets a different platform or ABI.");
        }
    }

    private static void verifyNativeIdentity(RuntimeReport report) {
        if (!report.runtimeId().equals(AssNativeProbe.runtimeId())
                || !report.configurationSha256().equals(AssNativeProbe.configurationSha256())
                || !"0.17.5".equals(report.componentVersions().get("libass"))
                || AssNativeProbe.libassVersion() != 0x01705000) {
            throw new KMediaAssRuntimeException(
                    "The loaded native ASS graph differs from its manifest.");
        }
    }

    static String platformClassifier() {
        String os = System.getProperty("os.name", "").toLowerCase(java.util.Locale.ROOT);
        String arch = System.getProperty("os.arch", "").toLowerCase(java.util.Locale.ROOT);
        String platform = os.contains("mac") ? "macos"
                : os.contains("win") ? "windows"
                : os.contains("linux") ? "linux" : "unsupported";
        String normalizedArch = arch.equals("amd64") || arch.equals("x86_64") ? "x86_64"
                : arch.equals("aarch64") || arch.equals("arm64") ? "aarch64" : "unsupported";
        if (platform.equals("unsupported")
                || normalizedArch.equals("unsupported")
                || (platform.equals("macos") && normalizedArch.equals("x86_64"))
                || (platform.equals("windows") && normalizedArch.equals("aarch64"))) {
            throw new KMediaAssRuntimeException(
                    "Unsupported desktop platform: " + platform + '-' + normalizedArch);
        }
        return platform + '-' + normalizedArch;
    }

    private static String sha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[64 * 1024];
                for (int count; (count = input.read(buffer)) >= 0; ) {
                    digest.update(buffer, 0, count);
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException impossible) {
            throw new AssertionError(impossible);
        }
    }

    private static void tighten(Path directory) {
        try {
            Files.setPosixFilePermissions(
                    directory,
                    Set.of(
                            PosixFilePermission.OWNER_READ,
                            PosixFilePermission.OWNER_WRITE,
                            PosixFilePermission.OWNER_EXECUTE));
        } catch (UnsupportedOperationException | IOException ignored) {
            // Windows ACLs are inherited from the user-owned temporary directory.
        }
    }

    private record RuntimeCandidate(
            Path sourceLibraryDirectory, String resourceBase, AssRuntimeManifest manifest) {}
}
