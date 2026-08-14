// SPDX-License-Identifier: LGPL-2.1-or-later

import com.android.build.api.dsl.LibraryExtension
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.publish.maven.tasks.PublishToMavenLocal
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository
import org.gradle.api.tasks.bundling.Jar

plugins {
    alias(libs.plugins.android.library)
    `maven-publish`
    signing
}

val nativePayloadDirectory = providers.gradleProperty("androidAssNativePayloadDirectory").map(::file)
val correspondingSourceArchive = providers.gradleProperty("correspondingSourceArchive").map(::file)
val expectedAbis = setOf("arm64-v8a", "armeabi-v7a")

extensions.configure<LibraryExtension> {
    namespace = "io.github.shusek.kmediaass.runtime.android"
    compileSdk = 37
    enableKotlin = false
    defaultConfig {
        minSdk = 23
        consumerProguardFiles("consumer-rules.pro")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    sourceSets.named("main") {
        java.srcDir(rootProject.file("runtime-shared/src/main/java").absolutePath)
        resources.srcDir(layout.buildDirectory.dir("generated/runtime-resources").get().asFile.absolutePath)
        jniLibs.srcDir(
            (nativePayloadDirectory.orNull?.resolve("jni")
                ?: layout.buildDirectory.dir("empty-jni").get().asFile).absolutePath,
        )
    }
    packaging.jniLibs.keepDebugSymbols.add("**/libkmediaffmpeg_*.so")
    publishing.singleVariant("release") { withSourcesJar() }
}

dependencies {
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach { useJUnitPlatform() }

val androidJavadocJar =
    tasks.register<Jar>("androidJavadocJar") {
        archiveClassifier.set("javadoc")
        isPreserveFileTimestamps = false
        isReproducibleFileOrder = true
        from(rootProject.file("README.md"))
        from(rootProject.file("LICENSE")) { into("META-INF") }
    }

val prepareRuntimeResources =
    tasks.register<Sync>("prepareRuntimeResources") {
        into(layout.buildDirectory.dir("generated/runtime-resources"))
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
        nativePayloadDirectory.orNull?.let { payload ->
            expectedAbis.forEach { abi ->
                from(payload.resolve("manifests/$abi/ass-runtime.properties")) { into("kmediaass/$abi") }
            }
        }
    }

tasks.named("preBuild") { dependsOn(prepareRuntimeResources) }
tasks.matching { it.name.startsWith("process") && it.name.endsWith("JavaRes") }.configureEach {
    dependsOn(prepareRuntimeResources)
}

val validateAndroidPayload =
    tasks.register("validateAndroidPayload") {
        nativePayloadDirectory.orNull?.let(inputs::dir)
        doLast {
            val payload = nativePayloadDirectory.orNull ?: return@doLast
            val jni = payload.resolve("jni")
            require(jni.isDirectory) { "Android ASS payload is missing jni/." }
            require(
                jni.listFiles().orEmpty().filter(File::isDirectory).map(File::getName).toSet() ==
                    expectedAbis,
            ) { "Android ASS payload must contain only arm64-v8a and armeabi-v7a." }
            expectedAbis.forEach { abi ->
                val libraries =
                    jni.resolve(abi).listFiles().orEmpty().filter(File::isFile).map(File::getName).toSet()
                require(
                    libraries.size == 5 &&
                        libraries.all { it.matches(Regex("libkmediaffmpeg_[A-Za-z0-9_.-]+\\.so")) },
                ) { "$abi must contain exactly the five ASS runtime libraries." }
                require(payload.resolve("manifests/$abi/ass-runtime.properties").isFile) {
                    "$abi ASS manifest is missing."
                }
            }
        }
    }

val requireReleaseInputs =
    tasks.register("requireReleaseInputs") {
        dependsOn(validateAndroidPayload)
        doLast {
            require(nativePayloadDirectory.isPresent) {
                "Android ASS publication requires -PandroidAssNativePayloadDirectory."
            }
            require(correspondingSourceArchive.isPresent && correspondingSourceArchive.get().isFile) {
                "Android ASS publication requires -PcorrespondingSourceArchive."
            }
        }
    }

tasks.withType<PublishToMavenRepository>().configureEach { dependsOn(requireReleaseInputs) }
tasks.withType<PublishToMavenLocal>().configureEach { dependsOn(requireReleaseInputs) }
tasks.named("check") { dependsOn(validateAndroidPayload) }

afterEvaluate {
    publishing {
        publications {
            create<MavenPublication>("release") {
                from(components["release"])
                artifactId = "kmedia-ass-runtime-android"
                artifact(androidJavadocJar)
                correspondingSourceArchive.orNull?.let { source ->
                    artifact(source) {
                        classifier = "corresponding-source"
                        extension = "tar.gz"
                    }
                }
                pom {
                    name.set("KMedia ASS Runtime for Android")
                    description.set("Shared, audited and replaceable libass text stack for Android.")
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
            }
        }
        repositories {
            rootProject.providers.gradleProperty("releaseRepository").orNull?.let { path ->
                maven { name = "release"; url = uri(path) }
            }
        }
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
