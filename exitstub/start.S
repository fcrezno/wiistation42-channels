/* Entry at 0x80001800. "STUBHAXX" must sit at 0x80001804 (libogc's __stub_found). */
	.section .text.start, "ax"
	.globl	_stub_start
_stub_start:
	b	1f
	.ascii	"STUBHAXX"
1:
	/* own small stack inside the stub area */
	lis	1, stub_stack_top@h
	ori	1, 1, stub_stack_top@l
	li	0, 0
	stwu	0, -16(1)
	bl	stub_main
2:	b	2b
