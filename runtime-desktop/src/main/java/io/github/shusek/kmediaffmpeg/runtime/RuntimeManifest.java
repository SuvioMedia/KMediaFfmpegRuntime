// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package io.github.shusek.kmediaffmpeg.runtime;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;

final class RuntimeManifest {
    static final List<String> COMPONENTS = List.of("ffmpeg", "freetype", "fribidi", "harfbuzz", "libass");

    final RuntimeReport report;
    final String assRuntimeId;
    final List<String> libraries;
    final Map<String, String> hashes;

    private RuntimeManifest(
            RuntimeReport report,
            String assRuntimeId,
            List<String> libraries,
            Map<String, String> hashes) {
        this.report = report;
        this.assRuntimeId = assRuntimeId;
        this.libraries = List.copyOf(libraries);
        this.hashes = Map.copyOf(hashes);
    }

    static RuntimeManifest read(InputStream input) throws IOException {
        Properties properties = new Properties();
        properties.load(input);
        Map<String, String> versions = new LinkedHashMap<>();
        Map<String, String> licenses = new LinkedHashMap<>();
        for (String component : COMPONENTS) {
            versions.put(component, required(properties, "version." + component));
            licenses.put(component, required(properties, "license." + component));
        }
        List<String> libraries = split(required(properties, "libraries"));
        if (libraries.size() != 7 || libraries.stream().distinct().count() != libraries.size()) {
            throw new IOException("The native library inventory is invalid.");
        }
        Map<String, String> hashes = new LinkedHashMap<>();
        for (String library : libraries) {
            if (!library.matches("[A-Za-z0-9_.-]+") || !library.toLowerCase().contains("kmediaffmpeg")) {
                throw new IOException("A native library name is outside the closed namespace.");
            }
            String hash = required(properties, "sha256." + library);
            if (!hash.matches("[0-9a-f]{64}")) {
                throw new IOException("A native library hash is malformed.");
            }
            hashes.put(library, hash);
        }
        RuntimeReport report = new RuntimeReport(
                required(properties, "runtimeId"),
                required(properties, "platform"),
                required(properties, "abi"),
                required(properties, "configurationSha256"),
                versions,
                licenses);
        return new RuntimeManifest(
                report, required(properties, "assRuntimeId"), libraries, hashes);
    }

    private static String required(Properties properties, String key) throws IOException {
        String value = properties.getProperty(key);
        if (value == null || value.isBlank() || value.indexOf('\0') >= 0) {
            throw new IOException("Missing or invalid runtime manifest field: " + key);
        }
        return value;
    }

    private static List<String> split(String value) {
        List<String> result = new ArrayList<>();
        for (String item : value.split(",", -1)) {
            if (!item.isBlank()) {
                result.add(item.trim());
            }
        }
        return result;
    }
}
