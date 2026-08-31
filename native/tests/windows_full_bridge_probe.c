// SPDX-License-Identifier: LGPL-2.1-or-later

#include <libavcodec/avcodec.h>
#include <libavfilter/avfilter.h>
#include <libavformat/avformat.h>
#include <stdio.h>

static int require_component(const void *component, const char *name) {
    if (component != NULL) return 0;
    fprintf(stderr, "Required Windows bridge component is missing: %s\n", name);
    return 1;
}

int main(void) {
    int failed = 0;
    failed |= require_component(avcodec_find_encoder_by_name("h264_mf"), "h264_mf encoder");
    failed |= require_component(avcodec_find_encoder(AV_CODEC_ID_AAC), "AAC encoder");
    failed |= require_component(avcodec_find_decoder(AV_CODEC_ID_H264), "H.264 decoder");
    failed |= require_component(avcodec_find_decoder(AV_CODEC_ID_HEVC), "HEVC decoder");
    failed |= require_component(avcodec_find_decoder(AV_CODEC_ID_WMV3), "WMV3 decoder");
    failed |= require_component(avcodec_find_decoder(AV_CODEC_ID_WMAPRO), "WMA Pro decoder");
    failed |= require_component(avfilter_get_by_name("buffer"), "buffer filter");
    failed |= require_component(avfilter_get_by_name("buffersink"), "buffersink filter");
    failed |= require_component(avfilter_get_by_name("subtitles"), "libass subtitles filter");
    failed |= require_component(avfilter_get_by_name("scale"), "scale filter");
    failed |= require_component(avfilter_get_by_name("format"), "format filter");
    failed |= require_component(av_find_input_format("avi"), "AVI demuxer");
    failed |= require_component(av_find_input_format("asf"), "ASF demuxer");
    failed |= require_component(av_guess_format("mp4", NULL, NULL), "MP4 muxer");
    if (failed != 0) return 1;
    puts("KMedia FFmpeg Windows full bridge components are available");
    return 0;
}
