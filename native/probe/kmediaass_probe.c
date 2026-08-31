// SPDX-License-Identifier: LGPL-2.1-or-later

#include <jni.h>
#include <ass/ass.h>
#include "ass_runtime_identity.h"

static jstring as_string(JNIEnv *env, const char *value) {
    return value == NULL ? NULL : (*env)->NewStringUTF(env, value);
}

JNIEXPORT jstring JNICALL
Java_cc_suviomedia_kmediaffmpeg_runtime_AssNativeProbe_runtimeId(JNIEnv *env, jclass ignored) {
    (void) ignored;
    return as_string(env, KMEDIAASS_RUNTIME_ID);
}

JNIEXPORT jstring JNICALL
Java_cc_suviomedia_kmediaffmpeg_runtime_AssNativeProbe_configurationSha256(
        JNIEnv *env, jclass ignored) {
    (void) ignored;
    return as_string(env, KMEDIAASS_CONFIGURATION_SHA256);
}

JNIEXPORT jint JNICALL
Java_cc_suviomedia_kmediaffmpeg_runtime_AssNativeProbe_libassVersion(JNIEnv *env, jclass ignored) {
    (void) env;
    (void) ignored;
    return ass_library_version();
}
