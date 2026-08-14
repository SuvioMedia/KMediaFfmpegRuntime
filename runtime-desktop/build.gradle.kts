// SPDX-License-Identifier: LGPL-2.1-or-later

import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.publish.maven.MavenPom
import org.gradle.api.publish.maven.tasks.PublishToMavenLocal
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository
import java.util.zip.ZipFile

plugins {
    `java-library`
    `maven-publish`
    signing
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
    withSourcesJar()
    withJavadocJar()
}

sourceSets.main {
    java.srcDir(rootProject.layout.projectDirectory.dir("runtime-ffmpeg-shared/src/main/java"))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    rootProject.providers.gradleProperty("kmediaFfmpegTestRuntime").orNull?.let { runtime ->
        systemProperty("kmediaFfmpegTestRuntime", runtime)
    }
    rootProject.providers.gradleProperty("kmediaFfmpegTestBundled").orNull?.let { bundled ->
        systemProperty("kmediaFfmpegTestBundled", bundled)
    }
}

dependencies {
    api(project(":kmedia-ass-runtime-desktop"))
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}

val nativePayloadDirectory = providers.gradleProperty("nativePayloadDirectory").map(::file)
val correspondingSourceArchive = providers.gradleProperty("correspondingSourceArchive").map(::file)

tasks.named<ProcessResources>("processResources") {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    from(rootProject.file("LICENSE")) { into("META-INF") }
    from(rootProject.file("NOTICE")) { into("META-INF") }
    from(rootProject.file("THIRD_PARTY_NOTICES.md")) { into("META-INF") }
    from(rootProject.file("docs/RELINKING.md")) { into("META-INF") }
    from(rootProject.file("LICENSES")) { into("META-INF/LICENSES") }
    nativePayloadDirectory.orNull?.let { payload ->
        from(payload.resolve("resources"))
    }
}

val verifyNoCheckedInNativePayload =
    tasks.register("verifyNoCheckedInNativePayload") {
        val forbidden =
            fileTree(projectDir) {
                exclude("build/**")
                include("**/*.a", "**/*.dll", "**/*.dylib", "**/*.lib", "**/*.o", "**/*.so", "**/*.so.*")
            }
        inputs.files(forbidden)
        doLast { require(forbidden.isEmpty) { "Native payloads must be supplied as explicit release inputs." } }
    }

val validateNativePayload =
    tasks.register("validateNativePayload") {
        nativePayloadDirectory.orNull?.let(inputs::dir)
        doLast {
            val payload = nativePayloadDirectory.orNull ?: return@doLast
            val root = payload.resolve("resources/META-INF/kmediaffmpeg/native")
            val expected = setOf("linux-x86_64", "linux-aarch64", "windows-x86_64", "macos-aarch64")
            require(root.isDirectory) { "Desktop payload is missing its native resource root." }
            require(root.listFiles().orEmpty().filter(File::isDirectory).map(File::getName).toSet() == expected) {
                "Desktop payload target matrix differs from policy."
            }
            expected.forEach { target ->
                require(root.resolve("$target/runtime.properties").isFile) { "$target manifest is missing." }
                require(root.resolve("$target/lib").isDirectory) { "$target libraries are missing." }
            }
        }
    }

val verifyRuntimeJar =
    tasks.register("verifyRuntimeJar") {
        dependsOn(tasks.named("jar"), validateNativePayload)
        val archive = tasks.named<Jar>("jar").flatMap { it.archiveFile }
        inputs.file(archive)
        doLast {
            ZipFile(archive.get().asFile).use { jar ->
                val names = jar.entries().asSequence().map { it.name }.toList()
                require(names.size == names.toSet().size) { "Runtime JAR contains duplicate entries." }
                require("META-INF/LICENSE" in names && "META-INF/NOTICE" in names && "META-INF/THIRD_PARTY_NOTICES.md" in names) {
                    "Runtime JAR legal inventory is incomplete."
                }
                require("META-INF/LICENSES/MIT.txt" in names && "META-INF/LICENSES/LGPL-2.1.txt" in names) {
                    "Runtime JAR must carry both loader choices and the native LGPL license."
                }
                require(names.none { it.endsWith(".a") || it.endsWith(".lib") || it.contains("x86_64-apple") }) {
                    "Runtime JAR contains a forbidden static or Intel Apple payload."
                }
            }
        }
    }

val requireReleaseInputs =
    tasks.register("requireReleaseInputs") {
        dependsOn(validateNativePayload)
        doLast {
            require(nativePayloadDirectory.isPresent) { "Desktop publication requires -PnativePayloadDirectory." }
            require(correspondingSourceArchive.isPresent && correspondingSourceArchive.get().isFile) {
                "Desktop publication requires -PcorrespondingSourceArchive."
            }
        }
    }

tasks.withType<PublishToMavenRepository>().configureEach { dependsOn(requireReleaseInputs) }
tasks.withType<PublishToMavenLocal>().configureEach { dependsOn(requireReleaseInputs) }
tasks.named("check") {
    dependsOn(verifyNoCheckedInNativePayload, verifyRuntimeJar)
}

publishing {
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
            artifactId = "kmedia-ffmpeg-runtime-desktop"
            correspondingSourceArchive.orNull?.let { source ->
                artifact(source) {
                    classifier = "corresponding-source"
                    extension = "tar.gz"
                }
            }
            pom { commonPom("KMedia FFmpeg Runtime for Desktop") }
        }
    }
    repositories {
        rootProject.providers.gradleProperty("releaseRepository").orNull?.let { path ->
            maven { name = "release"; url = uri(path) }
        }
    }
}

fun MavenPom.commonPom(displayName: String) {
    name.set(displayName)
    description.set("Shared, audited and replaceable FFmpeg 9.0.1 native runtime.")
    url.set("https://github.com/Shusek/KMediaFfmpegRuntime")
    inceptionYear.set("2026")
    licenses {
        license { name.set("MIT License (project-authored Java loader; dual-licensed)"); url.set("https://github.com/Shusek/KMediaFfmpegRuntime/blob/main/LICENSES/MIT.txt"); distribution.set("repo") }
        license { name.set("GNU Lesser General Public License, version 2.1 or later (alternative loader license and FFmpeg)"); url.set("https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html"); distribution.set("repo") }
    }
    developers { developer { id.set("Shusek"); name.set("Shusek") } }
    scm {
        connection.set("scm:git:https://github.com/Shusek/KMediaFfmpegRuntime.git")
        developerConnection.set("scm:git:ssh://git@github.com/Shusek/KMediaFfmpegRuntime.git")
        url.set("https://github.com/Shusek/KMediaFfmpegRuntime")
    }
}

signing {
    val key = providers.gradleProperty("signingInMemoryKey").orNull
    val password = providers.gradleProperty("signingPassword").orNull
    if (!key.isNullOrBlank()) {
        useInMemoryPgpKeys(key, password)
        sign(publishing.publications)
    }
}
