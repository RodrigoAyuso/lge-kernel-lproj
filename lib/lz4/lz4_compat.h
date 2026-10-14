/* SPDX-License-Identifier: GPL-2.0 */
/* Linux 3.4 adapter for the allocation-free LZ4 1.9.4 block API. */
#ifndef LZ4_KERNEL_COMPAT_H
#define LZ4_KERNEL_COMPAT_H

#include <linux/compiler.h>
#include <linux/types.h>
#include <linux/string.h>

/* The upstream codec has local offsets named current. */
#undef current

#define LZ4_FREESTANDING 1
#define LZ4HC_HEAPMODE 0
#define LZ4_memcpy __builtin_memcpy
#define LZ4_memmove __builtin_memmove
#define LZ4_memset __builtin_memset
#define LZ4_FORCE_INLINE static __always_inline
#define LZ4LIB_VISIBILITY static __maybe_unused
#define LZ4_PUBLISH_STATIC_FUNCTIONS
#define LZ4_DISABLE_DEPRECATE_WARNINGS

#endif
