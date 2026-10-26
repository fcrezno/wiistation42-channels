#!/bin/bash
# Builds exitstub.bin (flat, runs at 0x80001800). The forwarder zeroes 0x80001800-0x80003000, then copies it.
set -e
cd "$(dirname "$0")"
export PATH=/opt/devkitpro/devkitPPC/bin:$PATH
F="$EXTRA -mcpu=750 -meabi -mhard-float -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -msdata=none -G0 -Wall"
powerpc-eabi-gcc $F -c start.S -o start.o
powerpc-eabi-gcc $F -c stub.c -o stub.o
powerpc-eabi-ld -T stub.ld start.o stub.o -Map stub.map -o stub.elf
powerpc-eabi-objcopy -O binary -j .text -j .rodata -j .data stub.elf exitstub.bin
powerpc-eabi-nm -n stub.elf | grep -E "stub_stack_top|_stub_start|stub_main| req$| views$"
ls -la exitstub.bin
