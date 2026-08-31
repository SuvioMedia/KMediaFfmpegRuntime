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

val nativePayloadDirectory = providers.gradleProperty("androidNativePayloadDirectory").map(::file)
val correspondingSourceArchive = providers.gradleProperty("correspondingSourceArchive").map(::file)
val expectedAbis = setOf("arm64-v8a", "armeabi-v7a")

extensions.configure<LibraryExtension> {
    namespace = "cc.suviomedia.kmediaffmpeg.runtime.android"
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
        java.srcDir(rootProject.file("runtime-ffmpeg-shared/src/main/java").absolutePath)
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
    api(project(":kmedia-ass-runtime-android"))
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
            into("META-INF/kmediaffmpeg/legal")
        }
        from(rootProject.file("docs/RELINKING.md")) {
            into("META-INF/kmediaffmpeg/legal")
        }
        from(rootProject.file("LICENSES")) {
            into("META-INF/kmediaffmpeg/legal/LICENSES")
        }
        nativePayloadDirectory.orNull?.let { payload ->
            expectedAbis.forEach { abi ->
                from(payload.resolve("manifests/$abi/runtime.properties")) { into("kmediaffmpeg/$abi") }
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
            require(jni.isDirectory) { "Android payload is missing jni/." }
            require(jni.listFiles().orEmpty().filter(File::isDirectory).map(File::getName).toSet() == expectedAbis) {
                "Android payload must contain only arm64-v8a and armeabi-v7a."
            }
            expectedAbis.forEach { abi ->
                val libraries = jni.resolve(abi).listFiles().orEmpty().filter(File::isFile).map(File::getName).toSet()
                require(libraries.size == 7 && libraries.all { it.matches(Regex("libkmediaffmpeg_[A-Za-z0-9_.-]+\\.so")) }) {
                    "$abi must contain exactly the seven FFmpeg runtime libraries."
                }
                require(payload.resolve("manifests/$abi/runtime.properties").isFile) { "$abi manifest is missing." }
            }
        }
    }

val requireReleaseInputs =
    tasks.register("requireReleaseInputs") {
        dependsOn(validateAndroidPayload)
        doLast {
            require(nativePayloadDirectory.isPresent) { "Android publication requires -PandroidNativePayloadDirectory." }
            require(correspondingSourceArchive.isPresent && correspondingSourceArchive.get().isFile) {
                "Android publication requires -PcorrespondingSourceArchive."
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
                artifactId = "kmedia-ffmpeg-runtime-android"
                artifact(androidJavadocJar)
                correspondingSourceArchive.orNull?.let { source ->
                    artifact(source) {
                        classifier = "corresponding-source"
                        extension = "tar.gz"
                    }
                }
                pom {
                    name.set("KMedia FFmpeg Runtime for Android")
                    description.set("Shared, audited and replaceable FFmpeg 9.0.1 Android runtime.")
                    url.set("https://github.com/SuvioMedia/KMediaFfmpegRuntime")
                    inceptionYear.set("2026")
                    licenses {
                        license { name.set("MIT License (project-authored Java loader; dual-licensed)"); url.set("https://github.com/SuvioMedia/KMediaFfmpegRuntime/blob/main/LICENSES/MIT.txt"); distribution.set("repo") }
                        license { name.set("GNU Lesser General Public License, version 2.1 or later (alternative loader license and FFmpeg)"); url.set("https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html"); distribution.set("repo") }
                    }
                    developers { developer { id.set("Shusek"); name.set("Shusek") } }
                    scm {
                        connection.set("scm:git:https://github.com/SuvioMedia/KMediaFfmpegRuntime.git")
                        developerConnection.set("scm:git:ssh://git@github.com/SuvioMedia/KMediaFfmpegRuntime.git")
                        url.set("https://github.com/SuvioMedia/KMediaFfmpegRuntime")
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
