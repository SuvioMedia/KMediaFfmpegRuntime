// SPDX-License-Identifier: LGPL-2.1-or-later

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void *load_library(const char *name) {
    void *handle = dlopen(name, RTLD_NOW | RTLD_GLOBAL);
    if (handle == NULL) {
        fprintf(stderr, "dlopen(%s): %s\n", name, dlerror());
        exit(2);
    }
    return handle;
}

static void *load_symbol(void *handle, const char *name) {
    dlerror();
    void *symbol = dlsym(handle, name);
    const char *error = dlerror();
    if (error != NULL) {
        fprintf(stderr, "dlsym(%s): %s\n", name, error);
        exit(3);
    }
    return symbol;
}

int main(void) {
    static const char *const runtime_libraries[] = {
        "libkmediaffmpeg_freetype.so",
        "libkmediaffmpeg_fribidi.so",
        "libkmediaffmpeg_harfbuzz.so",
        "libkmediaffmpeg_avutil.so",
        "libkmediaffmpeg_swresample.so",
        "libkmediaffmpeg_swscale.so",
        "libkmediaffmpeg_avcodec.so",
        "libkmediaffmpeg_avformat.so",
        "libkmediaffmpeg_ass.so",
        "libkmediaffmpeg_avfilter.so",
        "libkmediaffmpeg_probe.so",
    };
    static const char *const client_libraries[] = {
        "libkmediampv_placebo.so",
        "libkmediampv_mpv.so",
        "libkmediampv_jni.so",
        "libkmediabridge.so",
    };

    void *avutil = NULL;
    void *ass = NULL;
    void *mpv = NULL;
    void *bridge = NULL;
    for (size_t index = 0; index < sizeof(runtime_libraries) / sizeof(runtime_libraries[0]); ++index) {
        void *handle = load_library(runtime_libraries[index]);
        if (strcmp(runtime_libraries[index], "libkmediaffmpeg_avutil.so") == 0) avutil = handle;
        if (strcmp(runtime_libraries[index], "libkmediaffmpeg_ass.so") == 0) ass = handle;
    }
    for (size_t index = 0; index < sizeof(client_libraries) / sizeof(client_libraries[0]); ++index) {
        void *handle = load_library(client_libraries[index]);
        if (strcmp(client_libraries[index], "libkmediampv_mpv.so") == 0) mpv = handle;
        if (strcmp(client_libraries[index], "libkmediabridge.so") == 0) bridge = handle;
    }

    const char *(*av_version_info)(void) = load_symbol(avutil, "av_version_info");
    unsigned int (*ass_library_version)(void) = load_symbol(ass, "ass_library_version");
    uint64_t (*mpv_client_api_version)(void) = load_symbol(mpv, "mpv_client_api_version");
    int (*kmb_abi_version)(void) = load_symbol(bridge, "kmb_abi_version");
    const char *(*kmb_ffmpeg_version)(void) = load_symbol(bridge, "kmb_ffmpeg_version");

    printf(
        "{\"abi\":\"armeabi-v7a\",\"runtimeLibraries\":%zu,\"clientLibraries\":%zu,"
        "\"ffmpeg\":\"%s\",\"libass\":%u,\"mpvClientApi\":%llu,"
        "\"bridgeAbi\":%d,\"bridgeFfmpeg\":\"%s\"}\n",
        sizeof(runtime_libraries) / sizeof(runtime_libraries[0]),
        sizeof(client_libraries) / sizeof(client_libraries[0]),
        av_version_info(), ass_library_version(),
        (unsigned long long)mpv_client_api_version(), kmb_abi_version(), kmb_ffmpeg_version()
    );
    return 0;
}
