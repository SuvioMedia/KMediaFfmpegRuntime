// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

import android.os.Build;
import android.annotation.SuppressLint;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

/** Process-wide loader and inspector for the shared Android native graph. */
public final class KMediaFfmpegRuntime {
    public static final int MIN_SDK = 23;
    public static final Set<String> SUPPORTED_ABIS = Collections.unmodifiableSet(
            new HashSet<>(Arrays.asList("arm64-v8a", "armeabi-v7a")));

    private static final Object LOCK = new Object();
    private static RuntimeReport current;
    private static KMediaFfmpegRuntimeException terminalFailure;

    private KMediaFfmpegRuntime() {}

    public static boolean isSupportedDevice() {
        return selectedAbi() != null;
    }

    public static RuntimeReport initialize(RuntimeSource source) {
        if (source == null) {
            throw new NullPointerException("source");
        }
        synchronized (LOCK) {
            if (terminalFailure != null) {
                throw terminalFailure;
            }
            if (!isSupportedDevice()) {
                throw new KMediaFfmpegRuntimeException(
                        "KMediaFfmpegRuntime requires Android API 23+ on arm64-v8a or armeabi-v7a.");
            }
            try {
                PreparedRuntime prepared = source instanceof RuntimeSource.Bundled
                        ? prepareBundled(selectedAbi())
                        : prepareExternal(((RuntimeSource.ExternalDirectory) source).directory());
                RuntimeReport assRuntime = KMediaAssRuntime.initialize(source);
                if (!prepared.manifest.assRuntimeId.equals(assRuntime.runtimeId())) {
                    throw new KMediaFfmpegRuntimeException(
                            "KMediaFfmpegRuntime requires a different KMediaAssRuntime ID.");
                }
                if (current != null) {
                    if (!current.runtimeId().equals(prepared.manifest.report.runtimeId())) {
                        throw new KMediaFfmpegRuntimeException(
                                "A different KMediaFfmpegRuntime is already initialized in this process.");
                    }
                    return current;
                }
                if (prepared.bundled) {
                    for (String library : prepared.manifest.libraries) {
                        System.loadLibrary(baseName(library));
                    }
                } else {
                    verifyExternalFiles(prepared.directory, prepared.manifest);
                    for (String library : prepared.manifest.libraries) {
                        System.load(new File(prepared.directory, library).getAbsolutePath());
                    }
                }
                verifyNativeIdentity(prepared.manifest.report);
                current = prepared.manifest.report;
                return current;
            } catch (KMediaFfmpegRuntimeException error) {
                if (current == null) {
                    terminalFailure = error;
                }
                throw error;
            } catch (Exception | LinkageError error) {
                terminalFailure = new KMediaFfmpegRuntimeException("The shared Android runtime could not be initialized.", error);
                throw terminalFailure;
            }
        }
    }

    /** Returns the selected runtime report, or null before initialization. */
    public static RuntimeReport currentOrNull() {
        synchronized (LOCK) {
            return current;
        }
    }

    private static PreparedRuntime prepareBundled(String abi) throws IOException {
        String resource = "/kmediaffmpeg/" + abi + "/runtime.properties";
        try (InputStream input = KMediaFfmpegRuntime.class.getResourceAsStream(resource)) {
            if (input == null) {
                throw new IOException("The bundled Android runtime manifest is missing for " + abi + '.');
            }
            AndroidRuntimeManifest manifest = AndroidRuntimeManifest.read(input);
            if (!manifest.report.platform().equals("android") || !manifest.report.abi().equals(abi)) {
                throw new IOException("The bundled Android runtime manifest targets another ABI.");
            }
            return new PreparedRuntime(null, manifest, true);
        }
    }

    @SuppressLint("UnsafeDynamicallyLoadedCode")
    private static PreparedRuntime prepareExternal(File root) throws IOException {
        File real = canonicalRealDirectory(root);
        if (!real.isDirectory()) {
            throw new IOException("The external Android runtime root is not a real directory.");
        }
        AndroidRuntimeManifest manifest;
        try (InputStream input = new FileInputStream(new File(real, "runtime.properties"))) {
            manifest = AndroidRuntimeManifest.read(input);
        }
        if (!manifest.report.platform().equals("android") || !manifest.report.abi().equals(selectedAbi())) {
            throw new IOException("The external Android runtime targets another ABI.");
        }
        return new PreparedRuntime(new File(real, "lib"), manifest, false);
    }

    private static void verifyExternalFiles(File root, AndroidRuntimeManifest manifest) throws IOException {
        File directory = canonicalRealDirectory(root);
        for (String library : manifest.libraries) {
            File file = new File(directory, library);
            if (!file.isFile() || !file.getCanonicalFile().equals(file.getAbsoluteFile())
                    || !sha256(file).equals(manifest.hashes.get(library))) {
                throw new IOException("An external Android native library failed verification.");
            }
        }
    }

    private static void verifyNativeIdentity(RuntimeReport report) {
        if (!report.runtimeId().equals(NativeProbe.runtimeId())
                || !report.configurationSha256().equals(NativeProbe.configurationSha256())
                || !report.componentVersions().get("ffmpeg").equals(NativeProbe.ffmpegVersion())
                || !NativeProbe.ffmpegLicense().startsWith("LGPL version 2.1")) {
            throw new KMediaFfmpegRuntimeException("The loaded native graph differs from its signed manifest.");
        }
    }

    private static String selectedAbi() {
        for (String abi : Build.SUPPORTED_ABIS) {
            if (SUPPORTED_ABIS.contains(abi)) {
                return abi;
            }
        }
        return null;
    }

    private static String baseName(String library) {
        return library.substring("lib".length(), library.length() - ".so".length());
    }

    private static File canonicalRealDirectory(File directory) throws IOException {
        File canonical = directory.getCanonicalFile();
        if (!canonical.equals(directory.getAbsoluteFile()) || !canonical.isDirectory()) {
            throw new IOException("External runtime paths must not contain symbolic links.");
        }
        return canonical;
    }

    private static String sha256(File file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = new FileInputStream(file)) {
                byte[] buffer = new byte[64 * 1024];
                for (int count; (count = input.read(buffer)) >= 0; ) {
                    digest.update(buffer, 0, count);
                }
            }
            StringBuilder result = new StringBuilder(64);
            for (byte value : digest.digest()) {
                result.append(String.format(java.util.Locale.ROOT, "%02x", value & 0xff));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new AssertionError(impossible);
        }
    }

    private static final class PreparedRuntime {
        final File directory;
        final AndroidRuntimeManifest manifest;
        final boolean bundled;

        PreparedRuntime(File directory, AndroidRuntimeManifest manifest, boolean bundled) {
            this.directory = directory;
            this.manifest = manifest;
            this.bundled = bundled;
        }
    }
}
