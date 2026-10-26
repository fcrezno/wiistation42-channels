OUTPUT_ARCH(powerpc:common)
ENTRY(_stub_start)
SECTIONS {
	. = 0x80001800;
	.text : { *(.text.start) *(.text .text.*) }
	.rodata : { *(.rodata .rodata.* .sdata2 .sdata2.*) }
	.data : { *(.data .data.* .sdata .sdata.*) }
	.bss : { *(.bss .bss.* .sbss .sbss.* COMMON) }
	. = ALIGN(32);
	. += 0x400;
	stub_stack_top = .;
	/DISCARD/ : { *(.comment) *(.eh_frame) *(.note*) }
	ASSERT(stub_stack_top <= 0x80003000, "stub too big: it must end before 0x80003000")
}
