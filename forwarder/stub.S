/* IOS starts the PPC at physical 0x3400 with the MMU off when a channel's boot
 * content is a DOL. This stub sets HID0, clears the BATs, sets the segment
 * registers, maps MEM1/MEM2 cached (0x8/0x9) and uncached (0xC/0xD), sets HID4,
 * then returns from interrupt into __app_start (libogc2 crt0) with translation on.
 * Same steps as the stub in WiiLink's own channel (read from its boot DOL). */
	.section .stub, "ax"
	.globl	__ws42_stub
__ws42_stub:
	lis	3, 0x0011
	ori	3, 3, 0x0c64
	mtspr	1008, 3		/* HID0 */
	isync
	li	4, 0x2000
	mtmsr	4		/* FP on, translation off */
	ori	3, 3, 0xc000
	mtspr	1008, 3		/* HID0: enable and flash-invalidate caches */
	isync

	li	0, 0
	mtspr	528, 0
	mtspr	530, 0
	mtspr	532, 0
	mtspr	534, 0
	mtspr	536, 0
	mtspr	538, 0
	mtspr	540, 0
	mtspr	542, 0
	mtspr	560, 0
	mtspr	562, 0
	mtspr	564, 0
	mtspr	566, 0
	mtspr	568, 0
	mtspr	570, 0
	mtspr	572, 0
	mtspr	574, 0
	isync

	lis	0, 0x8000
	mtsr	0, 0
	mtsr	1, 0
	mtsr	2, 0
	mtsr	3, 0
	mtsr	4, 0
	mtsr	5, 0
	mtsr	6, 0
	mtsr	7, 0
	mtsr	8, 0
	mtsr	9, 0
	mtsr	10, 0
	mtsr	11, 0
	mtsr	12, 0
	mtsr	13, 0
	mtsr	14, 0
	mtsr	15, 0
	isync

	/* BAT0: 0x80000000 -> 0x00000000, 256 MB, cached (MEM1) */
	li	3, 2
	lis	4, 0x8000
	ori	4, 4, 0x1fff
	mtspr	529, 3		/* IBAT0L */
	mtspr	528, 4		/* IBAT0U */
	mtspr	537, 3		/* DBAT0L */
	mtspr	536, 4		/* DBAT0U */
	isync
	/* BAT4: 0x90000000 -> 0x10000000, cached (MEM2) */
	addis	3, 3, 0x1000
	addis	4, 4, 0x1000
	mtspr	561, 3		/* IBAT4L */
	mtspr	560, 4		/* IBAT4U */
	mtspr	569, 3		/* DBAT4L */
	mtspr	568, 4		/* DBAT4U */
	isync
	/* DBAT1: 0xC0000000 -> 0x00000000, uncached */
	li	3, 0x2a
	lis	4, 0xc000
	ori	4, 4, 0x1fff
	mtspr	539, 3		/* DBAT1L */
	mtspr	538, 4		/* DBAT1U */
	isync
	/* DBAT5: 0xD0000000 -> 0x10000000, uncached */
	addis	3, 3, 0x1000
	addis	4, 4, 0x1000
	mtspr	571, 3		/* DBAT5L */
	mtspr	570, 4		/* DBAT5U */
	isync

	lis	3, 0x8200
	mtspr	1011, 3		/* HID4 */

	lis	3, __app_start@h
	ori	3, 3, __app_start@l
	mtsrr0	3
	mfmsr	3
	ori	3, 3, 0x30	/* IR | DR */
	mtsrr1	3
	rfi
