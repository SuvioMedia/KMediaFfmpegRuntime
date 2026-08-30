// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;

final class AssRuntimeManifest {
    static final List<String> COMPONENTS =
            List.of("freetype", "fribidi", "harfbuzz", "libass");

    final RuntimeReport report;
    final List<String> libraries;
    final Map<String, String> hashes;

    private AssRuntimeManifest(
            RuntimeReport report, List<String> libraries, Map<String, String> hashes) {
        this.report = report;
        this.libraries = List.copyOf(libraries);
        this.hashes = Map.copyOf(hashes);
    }

    static AssRuntimeManifest read(InputStream input) throws IOException {
        Properties properties = new Properties();
        properties.load(input);
        Map<String, String> versions = new LinkedHashMap<>();
        Map<String, String> licenses = new LinkedHashMap<>();
        for (String component : COMPONENTS) {
            versions.put(component, required(properties, "version." + component));
            licenses.put(component, required(properties, "license." + component));
        }
        List<String> libraries = split(required(properties, "libraries"));
        if (libraries.size() != 5 || libraries.stream().distinct().count() != libraries.size()) {
            throw new IOException("The native ASS library inventory is invalid.");
        }
        Map<String, String> hashes = new LinkedHashMap<>();
        for (String library : libraries) {
            if (!library.matches("[A-Za-z0-9_.-]+")
                    || !library.toLowerCase(java.util.Locale.ROOT).contains("kmediaffmpeg")) {
                throw new IOException("An ASS native library name is outside the closed namespace.");
            }
            String hash = required(properties, "sha256." + library);
            if (!hash.matches("[0-9a-f]{64}")) {
                throw new IOException("An ASS native library hash is malformed.");
            }
            hashes.put(library, hash);
        }
        return new AssRuntimeManifest(
                new RuntimeReport(
                        required(properties, "runtimeId"),
                        required(properties, "platform"),
                        required(properties, "abi"),
                        required(properties, "configurationSha256"),
                        versions,
                        licenses),
                libraries,
                hashes);
    }

    private static String required(Properties properties, String key) throws IOException {
        String value = properties.getProperty(key);
        if (value == null || value.isBlank() || value.indexOf('\0') >= 0) {
            throw new IOException("Missing or invalid ASS runtime manifest field: " + key);
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
