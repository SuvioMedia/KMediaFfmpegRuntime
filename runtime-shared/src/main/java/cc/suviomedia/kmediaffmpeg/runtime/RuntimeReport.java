// SPDX-License-Identifier: MIT OR LGPL-2.1-or-later
package cc.suviomedia.kmediaffmpeg.runtime;

import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/** Path-free immutable identity reported by the native runtime loaded in this process. */
public final class RuntimeReport {
    private final String runtimeId;
    private final String platform;
    private final String abi;
    private final String configurationSha256;
    private final Map<String, String> componentVersions;
    private final Map<String, String> componentLicenses;

    public RuntimeReport(
            String runtimeId,
            String platform,
            String abi,
            String configurationSha256,
            Map<String, String> componentVersions,
            Map<String, String> componentLicenses) {
        this.runtimeId = bounded(runtimeId, "runtimeId", 160);
        this.platform = bounded(platform, "platform", 32);
        this.abi = bounded(abi, "abi", 32);
        this.configurationSha256 = bounded(configurationSha256, "configurationSha256", 64);
        if (!this.configurationSha256.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("configurationSha256 must be lowercase SHA-256.");
        }
        this.componentVersions = closedMap(componentVersions, "componentVersions");
        this.componentLicenses = closedMap(componentLicenses, "componentLicenses");
        if (!this.componentVersions.keySet().equals(this.componentLicenses.keySet())) {
            throw new IllegalArgumentException("Version and license component inventories must match.");
        }
    }

    public String runtimeId() {
        return runtimeId;
    }

    public String platform() {
        return platform;
    }

    public String abi() {
        return abi;
    }

    public String configurationSha256() {
        return configurationSha256;
    }

    public Map<String, String> componentVersions() {
        return componentVersions;
    }

    public Map<String, String> componentLicenses() {
        return componentLicenses;
    }

    private static Map<String, String> closedMap(Map<String, String> source, String field) {
        Objects.requireNonNull(source, field);
        if (source.isEmpty() || source.size() > 16) {
            throw new IllegalArgumentException(field + " has an invalid size.");
        }
        TreeMap<String, String> result = new TreeMap<>();
        for (Map.Entry<String, String> entry : source.entrySet()) {
            result.put(
                    bounded(entry.getKey(), field + " key", 48),
                    bounded(entry.getValue(), field + " value", 96));
        }
        return Collections.unmodifiableMap(result);
    }

    private static String bounded(String value, String field, int maximum) {
        Objects.requireNonNull(value, field);
        if (value.trim().isEmpty() || value.length() > maximum || value.indexOf('\0') >= 0) {
            throw new IllegalArgumentException(field + " is blank, oversized, or contains NUL.");
        }
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof RuntimeReport)) {
            return false;
        }
        RuntimeReport report = (RuntimeReport) other;
        return runtimeId.equals(report.runtimeId)
                && platform.equals(report.platform)
                && abi.equals(report.abi)
                && configurationSha256.equals(report.configurationSha256)
                && componentVersions.equals(report.componentVersions)
                && componentLicenses.equals(report.componentLicenses);
    }

    @Override
    public int hashCode() {
        return Objects.hash(runtimeId, platform, abi, configurationSha256, componentVersions, componentLicenses);
    }

    @Override
    public String toString() {
        return "RuntimeReport{runtimeId='" + runtimeId + "', platform='" + platform
                + "', abi='" + abi + "', configurationSha256='" + configurationSha256
                + "', componentVersions=" + componentVersions + ", componentLicenses="
                + componentLicenses + "}";
    }
}
