// SPDX-License-Identifier: LGPL-2.1-or-later

import org.gradle.api.tasks.Exec

plugins {
    base
    alias(libs.plugins.android.library) apply false
}

val publicationVersion = providers.gradleProperty("publicationVersion").orElse("0.1.0-SNAPSHOT")

allprojects {
    group = "cc.suviomedia"
    version = publicationVersion.get()
}

val python = if (System.getProperty("os.name").startsWith("Windows")) "python" else "python3"

val verifyPolicy =
    tasks.register<Exec>("verifyPolicy") {
        group = "verification"
        description = "Verifies the closed component, platform, license, and feature policy."
        commandLine(python, "scripts/verify_policy.py", "--root", layout.projectDirectory.asFile.absolutePath)
    }

val verifyPublicationGraph =
    tasks.register("verifyPublicationGraph") {
        group = "verification"
        description = "Verifies the exact FFmpeg-to-ASS dependency boundary in generated POMs."
        dependsOn(
            ":kmedia-ass-runtime-desktop:generatePomFileForMavenPublication",
            ":kmedia-ffmpeg-runtime-desktop:generatePomFileForMavenPublication",
        )
        if (project.findProject(":kmedia-ffmpeg-runtime-android") != null) {
            dependsOn(
                ":kmedia-ass-runtime-android:generatePomFileForReleasePublication",
                ":kmedia-ffmpeg-runtime-android:generatePomFileForReleasePublication",
            )
        }

        doLast {
            val modules =
                buildList {
                    add(
                        Triple(
                            project(":kmedia-ass-runtime-desktop"),
                            "maven",
                            null,
                        ),
                    )
                    add(
                        Triple(
                            project(":kmedia-ffmpeg-runtime-desktop"),
                            "maven",
                            "kmedia-ass-runtime-desktop",
                        ),
                    )
                    if (project.findProject(":kmedia-ffmpeg-runtime-android") != null) {
                        add(
                            Triple(
                                project(":kmedia-ass-runtime-android"),
                                "release",
                                null,
                            ),
                        )
                        add(
                            Triple(
                                project(":kmedia-ffmpeg-runtime-android"),
                                "release",
                                "kmedia-ass-runtime-android",
                            ),
                        )
                    }
                }
            val dependencyPattern =
                Regex("<dependency>(.*?)</dependency>", setOf(RegexOption.DOT_MATCHES_ALL))

            modules.forEach { (module, publication, expectedAssArtifact) ->
                val pom =
                    module.layout.buildDirectory
                        .file("publications/$publication/pom-default.xml")
                        .get()
                        .asFile
                check(pom.isFile) { "Generated POM is missing for ${module.path}." }
                val dependencies =
                    dependencyPattern
                        .findAll(pom.readText())
                        .map { it.groupValues[1] }
                        .toList()
                if (expectedAssArtifact == null) {
                    check(dependencies.isEmpty()) {
                        "${module.path} must not acquire another runtime dependency."
                    }
                } else {
                    check(dependencies.size == 1) {
                        "${module.path} must publish exactly one runtime dependency."
                    }
                    val dependency = dependencies.single()
                    check("<groupId>cc.suviomedia</groupId>" in dependency)
                    check("<artifactId>$expectedAssArtifact</artifactId>" in dependency)
                    check("<version>${publicationVersion.get()}</version>" in dependency)
                    check("<scope>compile</scope>" in dependency)
                }
            }
        }
    }

tasks.named("check") {
    dependsOn(verifyPolicy, verifyPublicationGraph)
    dependsOn(":kmedia-ffmpeg-runtime-desktop:check")
    dependsOn(":kmedia-ass-runtime-desktop:check")
    if (project.findProject(":kmedia-ffmpeg-runtime-android") != null) {
        dependsOn(":kmedia-ffmpeg-runtime-android:check")
        dependsOn(":kmedia-ass-runtime-android:check")
    }
}
