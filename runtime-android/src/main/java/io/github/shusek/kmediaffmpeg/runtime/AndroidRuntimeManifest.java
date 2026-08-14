// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;

final class AndroidRuntimeManifest {
    private static final List<String> COMPONENTS =
            Collections.unmodifiableList(Arrays.asList("ffmpeg", "freetype", "fribidi", "harfbuzz", "libass"));

    final RuntimeReport report;
    final String assRuntimeId;
    final List<String> libraries;
    final Map<String, String> hashes;

    private AndroidRuntimeManifest(
            RuntimeReport report,
            String assRuntimeId,
            List<String> libraries,
            Map<String, String> hashes) {
        this.report = report;
        this.assRuntimeId = assRuntimeId;
        this.libraries = Collections.unmodifiableList(new ArrayList<>(libraries));
        this.hashes = Collections.unmodifiableMap(new LinkedHashMap<>(hashes));
    }

    static AndroidRuntimeManifest read(InputStream input) throws IOException {
        Properties properties = new Properties();
        properties.load(input);
        Map<String, String> versions = new LinkedHashMap<>();
        Map<String, String> licenses = new LinkedHashMap<>();
        for (String component : COMPONENTS) {
            versions.put(component, required(properties, "version." + component));
            licenses.put(component, required(properties, "license." + component));
        }
        List<String> libraries = new ArrayList<>();
        for (String item : required(properties, "libraries").split(",", -1)) {
            if (!item.trim().isEmpty()) {
                libraries.add(item.trim());
            }
        }
        if (libraries.size() != 7 || new HashSet<>(libraries).size() != libraries.size()) {
            throw new IOException("The Android native library inventory is invalid.");
        }
        Map<String, String> hashes = new LinkedHashMap<>();
        for (String library : libraries) {
            if (!library.matches("libkmediaffmpeg_[A-Za-z0-9_.-]+\\.so")) {
                throw new IOException("An Android native library is outside the closed namespace.");
            }
            String hash = required(properties, "sha256." + library);
            if (!hash.matches("[0-9a-f]{64}")) {
                throw new IOException("An Android native library hash is malformed.");
            }
            hashes.put(library, hash);
        }
        return new AndroidRuntimeManifest(
                new RuntimeReport(
                        required(properties, "runtimeId"),
                        required(properties, "platform"),
                        required(properties, "abi"),
                        required(properties, "configurationSha256"),
                        versions,
                        licenses),
                required(properties, "assRuntimeId"),
                libraries,
                hashes);
    }

    private static String required(Properties properties, String key) throws IOException {
        String value = properties.getProperty(key);
        if (value == null || value.trim().isEmpty() || value.indexOf('\0') >= 0) {
            throw new IOException("Missing or invalid Android runtime manifest field: " + key);
        }
        return value;
    }
}
