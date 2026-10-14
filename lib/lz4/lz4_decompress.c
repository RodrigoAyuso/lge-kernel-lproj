/*
 * LZ4 Decompressor for Linux kernel
 *
 * Copyright (C) 2013, LG Electronics, Kyungsik Lee <kyungsik.lee@lge.com>
 *
 * Based on LZ4 implementation by Yann Collet.
 *
 * LZ4 - Fast LZ compression algorithm
 * Copyright (C) 2011-2012, Yann Collet.
 * BSD 2-Clause License (http://www.opensource.org/licenses/bsd-license.php)
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 *
 *     * Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above
 * copyright notice, this list of conditions and the following disclaimer
 * in the documentation and/or other materials provided with the
 * distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 *  You can contact the author at :
 *  - LZ4 homepage : http://fastcompression.blogspot.com/p/lz4.html
 *  - LZ4 source repository : http://code.google.com/p/lz4/
 */

#ifndef STATIC
#include <linux/module.h>
#include <linux/kernel.h>
#endif
#include <linux/lz4.h>
#include "lz4_compat.h"
#include "upstream/lz4.c"

/* Preserve the legacy API: src_len is the consumed-byte count, not a bound. */
int lz4_decompress(const unsigned char *src, size_t *src_len,
		unsigned char *dest, size_t actual_dest_len)
{
	int consumed;

	if (actual_dest_len > LZ4_MAX_INPUT_SIZE)
		return -1;
	consumed = LZ4_decompress_fast((const char *)src, (char *)dest,
		actual_dest_len);
	if (consumed < 0)
		return -1;
	*src_len = consumed;
	return 0;
}
#ifndef STATIC
EXPORT_SYMBOL(lz4_decompress);
#endif

int lz4_decompress_unknownoutputsize(const unsigned char *src, size_t src_len,
		unsigned char *dest, size_t *dest_len)
{
	int out_len;

	if (src_len > LZ4_MAX_INPUT_SIZE || *dest_len > LZ4_MAX_INPUT_SIZE)
		return -1;
	out_len = LZ4_decompress_safe((const char *)src, (char *)dest,
		src_len, *dest_len);
	if (out_len < 0)
		return -1;
	*dest_len = out_len;
	return 0;
}
#ifndef STATIC
EXPORT_SYMBOL(lz4_decompress_unknownoutputsize);

MODULE_LICENSE("Dual BSD/GPL");
MODULE_DESCRIPTION("LZ4 1.9.4 decompressor");
#endif
