// SPDX-License-Identifier: LGPL-2.1-or-later

#include <glob.h>
#include <stddef.h>

int glob(const char *pattern, int flags, int (*error_callback)(const char *, int), glob_t *result) {
    (void) pattern;
    (void) flags;
    (void) error_callback;
    if (result != NULL) {
        result->gl_pathc = 0;
        result->gl_pathv = NULL;
        result->gl_offs = 0;
    }
    return GLOB_NOMATCH;
}

void globfree(glob_t *result) {
    (void) result;
}
