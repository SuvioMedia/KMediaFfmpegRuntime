// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Optional;

/** Process-wide loader and inspector for the shared desktop native graph. */
public final class KMediaFfmpegRuntime {
    private static final Object LOCK = new Object();
    private static RuntimeReport current;
    private static Path currentLibraryDirectory;
    private static KMediaFfmpegRuntimeException terminalFailure;

    private KMediaFfmpegRuntime() {}

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
                    RuntimeReport currentAss = KMediaAssRuntime.currentOrNull();
                    if (!current.runtimeId().equals(candidate.manifest.report.runtimeId())
                            || currentAss == null
                            || !candidate.manifest.assRuntimeId.equals(currentAss.runtimeId())) {
                        throw new KMediaFfmpegRuntimeException(
                                "A different KMediaFfmpegRuntime is already initialized in this process.");
                    }
                    return current;
                }
                RuntimeReport assRuntime = KMediaAssRuntime.initialize(source);
                if (!candidate.manifest.assRuntimeId.equals(assRuntime.runtimeId())) {
                    throw new KMediaFfmpegRuntimeException(
                            "KMediaFfmpegRuntime requires a different KMediaAssRuntime ID.");
                }
                verifyPlatform(candidate.manifest.report);
                Path libraryDirectory = KMediaAssRuntime.loadedLibraryDirectory();
                stageLibraries(candidate, libraryDirectory);
                for (String library : candidate.manifest.libraries) {
                    System.load(libraryDirectory.resolve(library).toAbsolutePath().toString());
                }
                verifyNativeIdentity(candidate.manifest.report);
                currentLibraryDirectory = libraryDirectory;
                current = candidate.manifest.report;
                return current;
            } catch (KMediaFfmpegRuntimeException error) {
                if (current == null) {
                    terminalFailure = error;
                }
                throw error;
            } catch (Exception | LinkageError error) {
                terminalFailure = new KMediaFfmpegRuntimeException("The shared native runtime could not be initialized.", error);
                throw terminalFailure;
            }
        }
    }

    public static Optional<RuntimeReport> current() {
        synchronized (LOCK) {
            return Optional.ofNullable(current);
        }
    }

    static Path loadedLibraryDirectory() {
        synchronized (LOCK) {
            if (currentLibraryDirectory == null) {
                throw new IllegalStateException("KMediaFfmpegRuntime is not initialized.");
            }
            return currentLibraryDirectory;
        }
    }

    private static RuntimeCandidate inspectExternal(File root) throws IOException {
        Path realRoot = root.toPath().toRealPath(LinkOption.NOFOLLOW_LINKS);
        if (!Files.isDirectory(realRoot, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("The external runtime root is not a real directory.");
        }
        RuntimeManifest manifest;
        try (InputStream input = Files.newInputStream(realRoot.resolve("runtime.properties"))) {
            manifest = RuntimeManifest.read(input);
        }
        Path libraryDirectory = realRoot.resolve("lib");
        validateLibraries(libraryDirectory, manifest);
        return new RuntimeCandidate(libraryDirectory, null, manifest);
    }

    private static RuntimeCandidate inspectBundled() throws IOException {
        String classifier = platformClassifier();
        String base = "/META-INF/kmediaffmpeg/native/" + classifier + "/";
        RuntimeManifest manifest;
        try (InputStream input = KMediaFfmpegRuntime.class.getResourceAsStream(base + "runtime.properties")) {
            if (input == null) {
                throw new IOException("No bundled runtime exists for " + classifier + '.');
            }
            manifest = RuntimeManifest.read(input);
        }
        return new RuntimeCandidate(null, base, manifest);
    }

    private static void stageLibraries(RuntimeCandidate candidate, Path libraryDirectory)
            throws IOException {
        Path realDirectory = libraryDirectory.toRealPath(LinkOption.NOFOLLOW_LINKS);
        if (!Files.isDirectory(realDirectory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("The shared process runtime directory is missing.");
        }
        for (String library : candidate.manifest.libraries) {
            Path output = realDirectory.resolve(library);
            if (Files.exists(output, LinkOption.NOFOLLOW_LINKS)) {
                throw new IOException("The FFmpeg runtime collides with the ASS runtime inventory.");
            }
            if (candidate.sourceLibraryDirectory != null) {
                Files.copy(candidate.sourceLibraryDirectory.resolve(library), output);
            } else {
                try (InputStream input =
                        KMediaFfmpegRuntime.class.getResourceAsStream(
                                candidate.resourceBase + "lib/" + library)) {
                    if (input == null) {
                        throw new IOException("A bundled native library is missing: " + library);
                    }
                    Files.copy(input, output);
                }
            }
        }
        validateLibraries(realDirectory, candidate.manifest);
    }

    private static void validateLibraries(Path directory, RuntimeManifest manifest) throws IOException {
        Path realDirectory = directory.toRealPath(LinkOption.NOFOLLOW_LINKS);
        if (!Files.isDirectory(realDirectory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("The runtime library directory is missing.");
        }
        for (String library : manifest.libraries) {
            Path file = realDirectory.resolve(library);
            if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(file)) {
                throw new IOException("A runtime library is not a real file.");
            }
            if (!sha256(file).equals(manifest.hashes.get(library))) {
                throw new IOException("A runtime library hash differs from its manifest.");
            }
        }
    }

    private static void verifyPlatform(RuntimeReport report) {
        String classifier = platformClassifier();
        String[] fields = classifier.split("-", 2);
        if (!report.platform().equals(fields[0]) || !report.abi().equals(fields[1])) {
            throw new KMediaFfmpegRuntimeException("The runtime manifest targets a different platform or ABI.");
        }
    }

    private static void verifyNativeIdentity(RuntimeReport report) {
        if (!report.runtimeId().equals(NativeProbe.runtimeId())
                || !report.configurationSha256().equals(NativeProbe.configurationSha256())
                || !report.componentVersions().get("ffmpeg").equals(NativeProbe.ffmpegVersion())
                || !NativeProbe.ffmpegLicense().startsWith("LGPL version 2.1")) {
            throw new KMediaFfmpegRuntimeException("The loaded native graph differs from its manifest.");
        }
    }

    private static String platformClassifier() {
        String os = System.getProperty("os.name", "").toLowerCase(java.util.Locale.ROOT);
        String arch = System.getProperty("os.arch", "").toLowerCase(java.util.Locale.ROOT);
        String platform = os.contains("mac") ? "macos" : os.contains("win") ? "windows" : os.contains("linux") ? "linux" : "unsupported";
        String normalizedArch = arch.equals("amd64") || arch.equals("x86_64") ? "x86_64"
                : arch.equals("aarch64") || arch.equals("arm64") ? "aarch64" : "unsupported";
        if (platform.equals("unsupported") || normalizedArch.equals("unsupported")
                || (platform.equals("macos") && normalizedArch.equals("x86_64"))
                || (platform.equals("windows") && normalizedArch.equals("aarch64"))) {
            throw new KMediaFfmpegRuntimeException("Unsupported desktop platform: " + platform + '-' + normalizedArch);
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

    private record RuntimeCandidate(
            Path sourceLibraryDirectory, String resourceBase, RuntimeManifest manifest) {}
}
