// SPDX-License-Identifier: LGPL-2.1-or-later

#include <jni.h>
#include <libavutil/avutil.h>
#include "runtime_identity.h"

static jstring as_string(JNIEnv *env, const char *value) {
    return value == NULL ? NULL : (*env)->NewStringUTF(env, value);
}

JNIEXPORT jstring JNICALL
Java_cc_suviomedia_kmediaffmpeg_runtime_NativeProbe_runtimeId(JNIEnv *env, jclass ignored) {
    (void) ignored;
    return as_string(env, KMEDIAFFMPEG_RUNTIME_ID);
}

JNIEXPORT jstring JNICALL
Java_cc_suviomedia_kmediaffmpeg_runtime_NativeProbe_configurationSha256(JNIEnv *env, jclass ignored) {
    (void) ignored;
    return as_string(env, KMEDIAFFMPEG_CONFIGURATION_SHA256);
}

JNIEXPORT jstring JNICALL
Java_cc_suviomedia_kmediaffmpeg_runtime_NativeProbe_ffmpegVersion(JNIEnv *env, jclass ignored) {
    (void) ignored;
    return as_string(env, av_version_info());
}

JNIEXPORT jstring JNICALL
Java_cc_suviomedia_kmediaffmpeg_runtime_NativeProbe_ffmpegLicense(JNIEnv *env, jclass ignored) {
    (void) ignored;
    return as_string(env, avutil_license());
}
