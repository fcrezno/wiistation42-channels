/* WiiStation 42 return stub. The forwarder copies it to 0x80001800 before it starts a game.
 * libogc's exit() finds "STUBHAXX" at 0x80001804 and jumps to 0x80001800 (the place the
 * Homebrew Channel uses for its own return stub). This code then asks IOS (ES) to launch the
 * hidden "Leave game" title 00010008-57535858 ("WSXX"), which offers Wii Menu or Homebrew Channel.
 *
 * Freestanding: no libogc. Raw IPC through the Hollywood registers, physical addresses,
 * caches flushed by hand. If the chooser is not installed, it launches the System Menu
 * (00000001-00000002) instead, so a missing chooser still ends at the Wii Menu.
 */
typedef unsigned int u32;
typedef unsigned long long u64;

#define IPC_PPCMSG  (*(volatile u32 *)0xCD000000)
#define IPC_PPCCTRL (*(volatile u32 *)0xCD000004)
#define IPC_ARMMSG  (*(volatile u32 *)0xCD000008)

#ifdef STAGE
#define HOLD(n) do { if (STAGE == (n)) for (;;) ; } while (0)
#else
#define HOLD(n) do { } while (0)
#endif

#define CHOOSER_TID 0x0001000857535858ULL   /* 00010008-WSXX */
#define SYSMENU_TID 0x0000000100000002ULL

struct ipc {
	u32 cmd;
	int result;
	int fd;
	u32 arg[5];
	u32 pad[8];
} __attribute__((aligned(32)));

static struct ipc req;
static u32 vec[8] __attribute__((aligned(32)));
static u64 tid __attribute__((aligned(32)));
static u32 count __attribute__((aligned(32)));
static unsigned char views[4 * 0xD8] __attribute__((aligned(32)));
static const char es_path[] __attribute__((aligned(32))) = "/dev/es";

static inline u32 phys(const void *p) { return (u32)p & 0x3FFFFFFF; }

static void flush(const void *p, u32 len)
{
	u32 a = (u32)p & ~31u, end = (u32)p + len;
	for (; a < end; a += 32) asm volatile("dcbf 0,%0" :: "r"(a) : "memory");
	asm volatile("sync" ::: "memory");
}

static void inval(const void *p, u32 len)
{
	u32 a = (u32)p & ~31u, end = (u32)p + len;
	for (; a < end; a += 32) asm volatile("dcbi 0,%0" :: "r"(a) : "memory");
	asm volatile("sync" ::: "memory");
}

static void bell(u32 bit) { IPC_PPCCTRL = (IPC_PPCCTRL & 0x30) | bit; }

static int call(void)
{
	flush(&req, sizeof(req));
	IPC_PPCMSG = phys(&req);
	bell(0x01);                                   /* X1: request sent */
	while (!(IPC_PPCCTRL & 0x02)) ;               /* Y2: IOS took it */
	bell(0x02);
	for (;;) {
		while (!(IPC_PPCCTRL & 0x04)) ;           /* Y1: a reply */
		u32 r = IPC_ARMMSG;
		bell(0x04);
		bell(0x08);                               /* X2: reply consumed */
		if (r == phys(&req)) break;
	}
	inval(&req, sizeof(req));
	return req.result;
}

static int es_ioctlv(int fd, u32 no, u32 in, u32 out)
{
	flush(vec, sizeof(vec));
	req.cmd = 7;                                  /* ioctlv */
	req.result = 0;
	req.fd = fd;
	req.arg[0] = no;
	req.arg[1] = in;
	req.arg[2] = out;
	req.arg[3] = phys(vec);
	return call();
}

static void launch(int fd, u64 title)
{
	tid = title;
	flush(&tid, 8);
	vec[0] = phys(&tid); vec[1] = 8;
	vec[2] = phys(&count); vec[3] = 4;
	count = 0;
	flush(&count, 4);
	if (es_ioctlv(fd, 0x12, 1, 1) < 0) return;    /* ES_GetNumTicketViews */
	HOLD(3);
	inval(&count, 4);
	if (count == 0 || count > 4) return;
	vec[0] = phys(&tid); vec[1] = 8;
	vec[2] = phys(&count); vec[3] = 4;
	vec[4] = phys(views); vec[5] = count * 0xD8;
	if (es_ioctlv(fd, 0x13, 2, 1) < 0) return;    /* ES_GetTicketViews */
	HOLD(4);
	inval(views, sizeof(views));
	flush(views, sizeof(views));
	vec[0] = phys(&tid); vec[1] = 8;
	vec[2] = phys(views); vec[3] = 0xD8;
	es_ioctlv(fd, 0x08, 2, 0);                    /* ES_LaunchTitle: does not return on success */
}

void stub_main(void)
{
	/* interrupts off: libogc's handlers are gone */
	u32 msr;
	asm volatile("mfmsr %0" : "=r"(msr));
	msr &= ~0x8000u;
	asm volatile("mtmsr %0; isync" :: "r"(msr));

	HOLD(0);
	IPC_PPCCTRL = 0x06;                           /* clear stale Y1/Y2, interrupts off */
	HOLD(1);

	req.cmd = 1;                                  /* open */
	req.result = 0;
	req.fd = 0;
	req.arg[0] = phys(es_path);
	req.arg[1] = 0;
	flush(es_path, sizeof(es_path));
	int fd = call();
	HOLD(2);
	if (fd >= 0) {
		launch(fd, CHOOSER_TID);
#ifndef NO_FALLBACK
		launch(fd, SYSMENU_TID);
#endif
	}
	for (;;) ;
}
