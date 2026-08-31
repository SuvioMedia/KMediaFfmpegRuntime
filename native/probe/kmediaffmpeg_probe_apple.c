// SPDX-License-Identifier: LGPL-2.1-or-later

#include <libavutil/avutil.h>
#include "runtime_identity.h"

const char *kmediaffmpeg_runtime_id(void) { return KMEDIAFFMPEG_RUNTIME_ID; }
const char *kmediaffmpeg_configuration_sha256(void) { return KMEDIAFFMPEG_CONFIGURATION_SHA256; }
const char *kmediaffmpeg_ffmpeg_version(void) { return av_version_info(); }
const char *kmediaffmpeg_ffmpeg_license(void) { return avutil_license(); }
