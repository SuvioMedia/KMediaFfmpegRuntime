// SPDX-License-Identifier: LGPL-2.1-or-later

// Checks the Linux x86-64 NVIDIA profile. On a machine without an NVIDIA driver
// (the default) the runtime must load, report the hardware codecs and fail to
// open them with an ordinary FFmpeg error. With KMEDIA_EXPECT_NVIDIA_DRIVER=1
// the CUDA device, h264_nvenc and hevc_nvenc must open and encode one frame;
// av1_nvenc needs an Ada or newer GPU and is required only with
// KMEDIA_EXPECT_NVIDIA_AV1=1.

#include <libavcodec/avcodec.h>
#include <libavutil/buffer.h>
#include <libavutil/error.h>
#include <libavutil/frame.h>
#include <libavutil/hwcontext.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failed;

static void fail(const char *message, const char *name) {
    fprintf(stderr, "FAIL: %s: %s\n", message, name);
    failed = 1;
}

static int decoder_offers_cuda(enum AVCodecID id) {
    const AVCodec *codec = avcodec_find_decoder(id);
    if (codec == NULL) return 0;
    for (int index = 0;; index++) {
        const AVCodecHWConfig *config = avcodec_get_hw_config(codec, index);
        if (config == NULL) return 0;
        if (config->device_type == AV_HWDEVICE_TYPE_CUDA &&
            (config->methods & AV_CODEC_HW_CONFIG_METHOD_HW_DEVICE_CTX) != 0) {
            return 1;
        }
    }
}

static int open_encoder(const char *name, int expect_driver, int required) {
    const AVCodec *codec = avcodec_find_encoder_by_name(name);
    if (codec == NULL) {
        fail("encoder is missing", name);
        return 0;
    }
    AVCodecContext *context = avcodec_alloc_context3(codec);
    AVFrame *frame = av_frame_alloc();
    AVPacket *packet = av_packet_alloc();
    if (context == NULL || frame == NULL || packet == NULL) {
        fail("allocation failed", name);
        return 0;
    }
    context->width = 1280;
    context->height = 720;
    context->pix_fmt = AV_PIX_FMT_YUV420P;
    context->time_base = (AVRational){1, 1000000};
    context->bit_rate = 4000000;
    context->max_b_frames = 0;
    int result = avcodec_open2(context, codec, NULL);
    char message[AV_ERROR_MAX_STRING_SIZE] = {0};
    if (result < 0) {
        av_strerror(result, message, sizeof(message));
        printf("%s did not open: %s\n", name, message);
        if (required) fail("encoder did not open with the NVIDIA driver", name);
    } else if (!expect_driver) {
        fail("encoder opened although no NVIDIA driver was expected", name);
    } else {
        frame->format = context->pix_fmt;
        frame->width = context->width;
        frame->height = context->height;
        frame->pts = 0;
        if (av_frame_get_buffer(frame, 0) < 0) {
            fail("frame allocation failed", name);
        } else {
            for (int plane = 0; plane < 3; plane++) {
                int rows = plane == 0 ? frame->height : frame->height / 2;
                memset(frame->data[plane], plane == 0 ? 96 : 128, (size_t)frame->linesize[plane] * rows);
            }
            int packets = 0;
            if (avcodec_send_frame(context, frame) < 0 || avcodec_send_frame(context, NULL) < 0) {
                fail("encoder rejected a frame", name);
            }
            while (avcodec_receive_packet(context, packet) == 0) {
                packets++;
                av_packet_unref(packet);
            }
            if (packets != 1) fail("encoder did not return exactly one packet", name);
            else printf("%s encoded one frame\n", name);
        }
    }
    av_packet_free(&packet);
    av_frame_free(&frame);
    avcodec_free_context(&context);
    return 1;
}

int main(void) {
    const char *expected = getenv("KMEDIA_EXPECT_NVIDIA_DRIVER");
    const int expect_driver = expected != NULL && strcmp(expected, "1") == 0;
    const char *configuration = avcodec_configuration();
    const char *flags[] = {
        "--enable-ffnvcodec", "--enable-cuda", "--enable-nvdec", "--enable-nvenc", "--enable-x86asm",
    };
    for (size_t index = 0; index < sizeof(flags) / sizeof(flags[0]); index++) {
        if (strstr(configuration, flags[index]) == NULL) fail("configuration lacks", flags[index]);
    }
    if (av_hwdevice_find_type_by_name("cuda") != AV_HWDEVICE_TYPE_CUDA) fail("hardware context is missing", "cuda");
    const struct { enum AVCodecID id; const char *name; } decoders[] = {
        {AV_CODEC_ID_H264, "h264"}, {AV_CODEC_ID_HEVC, "hevc"}, {AV_CODEC_ID_AV1, "av1"}, {AV_CODEC_ID_VP9, "vp9"},
    };
    for (size_t index = 0; index < sizeof(decoders) / sizeof(decoders[0]); index++) {
        if (!decoder_offers_cuda(decoders[index].id)) fail("decoder offers no NVDEC hwaccel", decoders[index].name);
    }
    AVBufferRef *device = NULL;
    int result = av_hwdevice_ctx_create(&device, AV_HWDEVICE_TYPE_CUDA, NULL, NULL, 0);
    if (result < 0) {
        char message[AV_ERROR_MAX_STRING_SIZE] = {0};
        av_strerror(result, message, sizeof(message));
        printf("CUDA device did not open: %s\n", message);
        if (expect_driver) fail("CUDA device did not open with the NVIDIA driver", "cuda");
    } else {
        printf("CUDA device opened\n");
        if (!expect_driver) fail("CUDA device opened although no NVIDIA driver was expected", "cuda");
        av_buffer_unref(&device);
    }
    const char *av1 = getenv("KMEDIA_EXPECT_NVIDIA_AV1");
    open_encoder("h264_nvenc", expect_driver, expect_driver);
    open_encoder("hevc_nvenc", expect_driver, expect_driver);
    open_encoder("av1_nvenc", expect_driver, expect_driver && av1 != NULL && strcmp(av1, "1") == 0);
    if (failed) return 1;
    printf("KMedia FFmpeg Linux NVIDIA profile verified (%s)\n", expect_driver ? "with driver" : "without driver");
    return 0;
}
