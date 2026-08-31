// SPDX-License-Identifier: LGPL-2.1-or-later

#include <ass/ass.h>
#include "ass_runtime_identity.h"

const char *kmediaass_runtime_id(void) { return KMEDIAASS_RUNTIME_ID; }
const char *kmediaass_configuration_sha256(void) { return KMEDIAASS_CONFIGURATION_SHA256; }
int kmediaass_libass_version(void) { return ass_library_version(); }
