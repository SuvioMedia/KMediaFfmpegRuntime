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
    java.srcDir(rootProject.layout.projectDirectory.dir("runtime-shared/src/main/java"))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    rootProject.providers.gradleProperty("kmediaAssTestRuntime").orNull?.let { runtime ->
        systemProperty("kmediaAssTestRuntime", runtime)
    }
    rootProject.providers.gradleProperty("kmediaAssTestBundled").orNull?.let { bundled ->
        systemProperty("kmediaAssTestBundled", bundled)
    }
}

dependencies {
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}

val nativePayloadDirectory = providers.gradleProperty("assNativePayloadDirectory").map(::file)
val correspondingSourceArchive = providers.gradleProperty("correspondingSourceArchive").map(::file)

tasks.named<ProcessResources>("processResources") {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    from(rootProject.file("LICENSE")) { into("META-INF") }
    from(rootProject.file("NOTICE")) { into("META-INF") }
    from(rootProject.file("THIRD_PARTY_NOTICES.md")) {
        into("META-INF/kmediaass/legal")
    }
    from(rootProject.file("docs/RELINKING.md")) {
        into("META-INF/kmediaass/legal")
    }
    from(rootProject.file("LICENSES")) {
        into("META-INF/kmediaass/legal/LICENSES")
    }
    nativePayloadDirectory.orNull?.let { payload -> from(payload.resolve("resources")) }
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
            val root = payload.resolve("resources/META-INF/kmediaass/native")
            val expected = setOf("linux-x86_64", "linux-aarch64", "windows-x86_64", "macos-aarch64")
            require(root.isDirectory) { "Desktop ASS payload is missing its native resource root." }
            require(root.listFiles().orEmpty().filter(File::isDirectory).map(File::getName).toSet() == expected) {
                "Desktop ASS payload target matrix differs from policy."
            }
            expected.forEach { target ->
                require(root.resolve("$target/ass-runtime.properties").isFile) {
                    "$target ASS manifest is missing."
                }
                val libraries = root.resolve("$target/lib").listFiles().orEmpty().filter(File::isFile)
                require(libraries.size == 5) { "$target must contain exactly five ASS runtime libraries." }
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
                require(names.size == names.toSet().size) { "ASS runtime JAR contains duplicate entries." }
                val legalRoot = "META-INF/kmediaass/legal"
                require(
                    "META-INF/LICENSE" in names &&
                        "META-INF/NOTICE" in names &&
                        "$legalRoot/THIRD_PARTY_NOTICES.md" in names &&
                        "$legalRoot/RELINKING.md" in names,
                ) {
                    "ASS runtime JAR legal inventory is incomplete."
                }
                require(
                    "$legalRoot/LICENSES/MIT.txt" in names &&
                        "$legalRoot/LICENSES/LGPL-2.1.txt" in names,
                ) {
                    "ASS runtime JAR must carry both loader choices and the native LGPL license."
                }
                require(names.none { it.endsWith(".a") || it.endsWith(".lib") || it.contains("x86_64-apple") }) {
                    "ASS runtime JAR contains a forbidden static or Intel Apple payload."
                }
            }
        }
    }

val requireReleaseInputs =
    tasks.register("requireReleaseInputs") {
        dependsOn(validateNativePayload)
        doLast {
            require(nativePayloadDirectory.isPresent) {
                "Desktop ASS publication requires -PassNativePayloadDirectory."
            }
            require(correspondingSourceArchive.isPresent && correspondingSourceArchive.get().isFile) {
                "Desktop ASS publication requires -PcorrespondingSourceArchive."
            }
        }
    }

tasks.withType<PublishToMavenRepository>().configureEach { dependsOn(requireReleaseInputs) }
tasks.withType<PublishToMavenLocal>().configureEach { dependsOn(requireReleaseInputs) }
tasks.named("check") { dependsOn(verifyNoCheckedInNativePayload, verifyRuntimeJar) }

publishing {
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
            artifactId = "kmedia-ass-runtime-desktop"
            correspondingSourceArchive.orNull?.let { source ->
                artifact(source) {
                    classifier = "corresponding-source"
                    extension = "tar.gz"
                }
            }
            pom { commonPom("KMedia ASS Runtime for Desktop") }
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
    description.set("Shared, audited and replaceable libass text stack for desktop.")
    url.set("https://github.com/Shusek/KMediaFfmpegRuntime")
    inceptionYear.set("2026")
    licenses {
        license { name.set("MIT License (project-authored Java loader; dual-licensed)"); url.set("https://github.com/Shusek/KMediaFfmpegRuntime/blob/main/LICENSES/MIT.txt"); distribution.set("repo") }
        license { name.set("GNU Lesser General Public License, version 2.1 or later (alternative loader license and FriBidi)"); url.set("https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html"); distribution.set("repo") }
        license { name.set("ISC License (libass)"); url.set("https://github.com/libass/libass/blob/0.17.5/COPYING"); distribution.set("repo") }
        license { name.set("FreeType License"); url.set("https://freetype.org/license.html"); distribution.set("repo") }
        license { name.set("MIT License (HarfBuzz)"); url.set("https://github.com/harfbuzz/harfbuzz/blob/12.2.0/COPYING"); distribution.set("repo") }
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
