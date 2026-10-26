/* WiiStation 42 game channel forwarder.
 *
 * Boots straight from the channel (content 1). Mounts the USB drive (or the SD
 * card), loads one boot.dol into MEM2, checks it, then copies it into
 * place and jumps to it with arguments, so the emulator or Nintendont starts
 * the game with no menu.
 *
 * One build serves every channel: tools/makechannel.py writes the game's
 * values into the cfg block below (found by its magic).
 *
 * Linked at 0x81400000, so the target (vbagx's bss reaches 0x81177040) and its
 * argument block always sit below this program, its heap and its stack.
 */
#include <gccore.h>
#include <ogc/usbstorage.h>
#include <sdcard/wiisd_io.h>
#include <fat.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define ARGV_MAGIC   0x5f617267
#define TARGET_LO    0x80003000u
#define TARGET_HI    0x81400000u   /* this program starts here */

typedef struct {
	char magic[8];          /* "WS42FWD1" */
	char title[64];         /* shown only on an error screen */
	char dol[128];          /* e.g. usb:/apps/vbagx/boot.dol */
	u32  args_len;          /* bytes used in args */
	u8   args[2048];        /* argv[0]\0argv[1]\0... (raw; Nintendont's argv[1] is a binary NIN_CFG) */
	u32  flags;             /* 1 = reload IOS 58 before the jump, like the Homebrew Channel (emulators) */
} fwd_cfg;

__attribute__((used, aligned(32)))
volatile fwd_cfg cfg = { "WS42FWD1", "WiiStation 42 game", "usb:/apps/vbagx/boot.dol", 0, {0}, 0 };

typedef struct {
	u32 toff[7], doff[11];
	u32 taddr[7], daddr[11];
	u32 tsize[7], dsize[11];
	u32 bss, bsize, entry;
	u32 pad[7];
} dolhdr;

struct ogc_argv {
	int argvMagic;
	char *commandLine;
	int length;
	int argc;
	char **argv;
	char **endARGV;
};

extern void __exception_closeall(void);
extern const u8 exitstub_bin[];
extern const u32 exitstub_bin_size;

static GXRModeObj *rmode;

#ifdef DEBUG_STEPS
#define STEP(s) do { printf("    %s\n", s); for (int _i = 0; _i < 120; _i++) VIDEO_WaitVSync(); } while (0)
#else
#define STEP(s) do { } while (0)
#endif

/* Loading picture: makechannel.py adds a DOL data section at 0x80800000 holding "WSLD" + 28 bytes
 * + a 640x480 YUY2 picture (title screen, name, empty bar). That area is free until the game is
 * copied into place, and by then the picture is already in the framebuffer. */
#define LOAD_PIC   0x80800000u
#define BAR_X      120
#define BAR_Y      420
#define BAR_W      400
#define BAR_H      10

static u32 *xfb;
static int pic_shown;

static void console_on(void)
{
	VIDEO_ClearFrameBuffer(rmode, xfb, COLOR_BLACK);
	console_init(xfb, 20, 20, rmode->fbWidth, rmode->xfbHeight, rmode->fbWidth * VI_DISPLAY_PIX_SZ);
}

static void video_init(void)
{
	VIDEO_Init();
	rmode = VIDEO_GetPreferredMode(NULL);
	xfb = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
	VIDEO_ClearFrameBuffer(rmode, xfb, COLOR_BLACK);
	if (*(volatile u32 *)LOAD_PIC == 0x57534C44) {          /* "WSLD" */
		const u8 *src = (const u8 *)(LOAD_PIC + 32);
		int h = rmode->xfbHeight < 480 ? rmode->xfbHeight : 480;
		int w = rmode->fbWidth < 640 ? rmode->fbWidth : 640;
		int y0 = (rmode->xfbHeight - h) / 2;
		for (int y = 0; y < h; y++)
			memcpy((u8 *)xfb + (y0 + y) * rmode->fbWidth * 2, src + y * 640 * 2, w * 2);
		pic_shown = 1;
	} else {
		console_init(xfb, 20, 20, rmode->fbWidth, rmode->xfbHeight, rmode->fbWidth * VI_DISPLAY_PIX_SZ);
	}
	VIDEO_Configure(rmode);
	VIDEO_SetNextFramebuffer(xfb);
	VIDEO_SetBlack(FALSE);
	VIDEO_Flush();
	VIDEO_WaitVSync();
	if (rmode->viTVMode & VI_NON_INTERLACE) VIDEO_WaitVSync();
}

/* Fills the loading bar to done/total (white, YUY2 0xEB80EB80). */
static void bar(u32 done, u32 total)
{
	if (!pic_shown || !total) return;
	int y0 = (rmode->xfbHeight - 480) / 2;
	if (y0 < 0) y0 = 0;
	int w = (int)((u64)BAR_W * done / total) & ~1;
	for (int y = BAR_Y; y < BAR_Y + BAR_H; y++) {
		u32 *row = xfb + ((y0 + y) * rmode->fbWidth + BAR_X) / 2;
		for (int x = 0; x < w / 2; x++) row[x] = 0xEB80EB80;
	}
}

static void fail(const char *why, const char *detail)
{
	if (pic_shown) console_on();
	printf("\n\n\n    %s\n\n    %s\n    %s\n\n    Back to the Wii Menu in 10 seconds.\n",
	       (const char *)cfg.title, why, detail ? detail : "");
	sleep(10);
	SYS_ResetSystem(SYS_RETURNTOMENU, 0, 0);
	for (;;) VIDEO_WaitVSync();
}

static bool mount_usb(void)
{
	/* Large USB hard drives need a few seconds to spin up: try for 20 s. */
	for (int i = 0; i < 40; i++) {
		if (__io_usbstorage.startup(&__io_usbstorage) && __io_usbstorage.isInserted(&__io_usbstorage))
			return fatMountSimple("usb", &__io_usbstorage);
		usleep(500000);
	}
	return false;
}

int main(int argc, char **argv)
{
	char path[129];
	memcpy(path, (const void *)cfg.dol, 128);
	path[128] = 0;

	video_init();
	/* No loading screen: plain black until the game appears (errors still print). */
	VIDEO_WaitVSync();

	if (cfg.args_len > sizeof(cfg.args) - 2)
		fail("The channel settings are damaged.", NULL);
	/* "sd:" paths are for the Dolphin test (Dolphin has no USB drive); the real channels use "usb:". */
	bool sd = strncmp(path, "sd:", 3) == 0;
	if (sd ? !fatMountSimple("sd", &__io_wiisd) : !mount_usb())
		fail(sd ? "The SD card did not answer." : "The USB drive did not answer.",
		     sd ? "Is the SD card in the Wii?" : "Is the USB drive connected to the Wii?");

	STEP("mounted");
	FILE *f = fopen(path, "rb");
	if (!f) fail("This file is missing:", path);
	fseek(f, 0, SEEK_END);
	long size = ftell(f);
	fseek(f, 0, SEEK_SET);
	if (size < (long)sizeof(dolhdr) || size > 16 * 1024 * 1024) fail("This file is not a program:", path);

	u8 *buf = (u8 *)(((u32)SYS_GetArena2Lo() + 31) & ~31u);
	SYS_SetArena2Lo(buf + size + 32);
	for (long got = 0; got < size; ) {                      /* in pieces, so the bar moves */
		long n = size - got > 256 * 1024 ? 256 * 1024 : size - got;
		if (fread(buf + got, 1, n, f) != (size_t)n) fail("Could not read:", path);
		got += n;
		bar(got, size);
#ifdef LOAD_HOLD
		usleep(400000);   /* test only: slow the bar down so Dolphin captures can see it */
#endif
	}
	fclose(f);

	STEP("read");
	dolhdr *h = (dolhdr *)buf;
	u32 top = 0;
	for (int i = 0; i < 18; i++) {
		u32 off = i < 7 ? h->toff[i] : h->doff[i - 7];
		u32 addr = i < 7 ? h->taddr[i] : h->daddr[i - 7];
		u32 len = i < 7 ? h->tsize[i] : h->dsize[i - 7];
		if (!len) continue;
		if (off + len > (u32)size || off + len < off) fail("The program file is cut short:", path);
		if (addr < TARGET_LO || addr + len > TARGET_HI || addr + len < addr) fail("The program loads to a bad address:", path);
		if (addr + len > top) top = addr + len;
	}
	if (h->bss + h->bsize > top) top = h->bss + h->bsize;
	top = (top + 31) & ~31u;
	if (top + cfg.args_len + 1024 > TARGET_HI) fail("The program is too large for this forwarder:", path);
	u32 entry = h->entry;
	STEP("checked");
#ifdef DEBUG_STEPS
	printf("    buf %p size %ld top %08x entry %08x\n", buf, size, (unsigned)top, (unsigned)entry);
	STEP("jumping");
#endif
	if (entry < TARGET_LO || entry >= TARGET_HI) fail("The program has a bad start address:", path);

	if (sd) {
		fatUnmount("sd");
		__io_wiisd.shutdown(&__io_wiisd);
	} else {
		fatUnmount("usb");
		__io_usbstorage.shutdown(&__io_usbstorage);
	}

	VIDEO_SetBlack(TRUE);
	VIDEO_Flush();
	VIDEO_WaitVSync();

	/* The emulators expect a fresh USB stack, as the Homebrew Channel gives them by reloading
	 * IOS. Nintendont must NOT get this: it needs the AHBPROT access that a reload removes. */
	if (cfg.flags & 1)
		IOS_ReloadIOS(58);

	SYS_ResetSystem(SYS_SHUTDOWN, 0, 0);

	IRQ_Disable();

	__exception_closeall();

	for (int i = 0; i < 18; i++) {
		u32 off = i < 7 ? h->toff[i] : h->doff[i - 7];
		u32 addr = i < 7 ? h->taddr[i] : h->daddr[i - 7];
		u32 len = i < 7 ? h->tsize[i] : h->dsize[i - 7];
		if (!len) continue;
		memcpy((void *)addr, buf + off, len);
		DCFlushRange((void *)addr, len);
		ICInvalidateRange((void *)addr, len);
	}

	/* Arguments go after the program's bss, the place the Homebrew Channel uses. */
	if (cfg.args_len && *(volatile u32 *)(entry + 4) == ARGV_MAGIC) {
		char *cmd = (char *)top;
		memcpy(cmd, (const void *)cfg.args, cfg.args_len);
		cmd[cfg.args_len] = 0;
		cmd[cfg.args_len + 1] = 0;
		DCFlushRange(cmd, cfg.args_len + 2);
		struct ogc_argv *a = (struct ogc_argv *)(entry + 8);
		memset(a, 0, sizeof(*a));
		a->argvMagic = ARGV_MAGIC;
		a->commandLine = cmd;
		a->length = cfg.args_len + 1;
		DCFlushRange(a, sizeof(*a));
	}

	/* No return stub, like Virtual Console: exiting a game goes back to the Wii Menu.
	 * (exitstub/ is an unused "Leave game" stub, kept so the build stays the same.) */
	memset((void *)0x80001800, 0, 0x1800);
	DCFlushRange((void *)0x80001800, 0x1800);
	ICInvalidateRange((void *)0x80001800, 0x1800);

	((void (*)(void))entry)();
	return 0;
}
