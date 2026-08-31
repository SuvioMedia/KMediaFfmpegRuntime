// SPDX-License-Identifier: LGPL-2.1-or-later

pluginManagement {
    repositories {
        google()
        gradlePluginPortal()
        mavenCentral()
    }
}

plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "KMediaFfmpegRuntime"

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

val desktopOnly =
    providers.gradleProperty("kmediaFfmpegDesktopOnly").orNull?.toBooleanStrictOrNull() ?: false

include(":kmedia-ffmpeg-runtime-desktop")
project(":kmedia-ffmpeg-runtime-desktop").projectDir = file("runtime-desktop")
include(":kmedia-ass-runtime-desktop")
project(":kmedia-ass-runtime-desktop").projectDir = file("ass-runtime-desktop")
if (!desktopOnly) {
    include(":kmedia-ffmpeg-runtime-android")
    project(":kmedia-ffmpeg-runtime-android").projectDir = file("runtime-android")
    include(":kmedia-ass-runtime-android")
    project(":kmedia-ass-runtime-android").projectDir = file("ass-runtime-android")
}
