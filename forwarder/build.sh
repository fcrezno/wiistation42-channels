#!/bin/bash
# Builds forwarder.dol with the local devkitPPC + libogc2 (C:\msys64\opt\devkitpro).
set -e
cd "$(dirname "$0")"
export DEVKITPRO=/opt/devkitpro DEVKITPPC=/opt/devkitpro/devkitPPC
export PATH=$DEVKITPPC/bin:$DEVKITPRO/tools/bin:$PATH
M="-DGEKKO -mrvl -mcpu=750 -meabi -mhard-float"
I=$DEVKITPRO/libogc2/wii
powerpc-eabi-gcc $M -O2 -Wall $EXTRA -I$I/include -c forwarder.c -o forwarder.o
powerpc-eabi-gcc $M -c stub.S -o stub.o
bash ../exitstub/build.sh > /dev/null
(cd ../exitstub && bin2s -a 32 exitstub.bin > ../forwarder/exitstub_bin.s)
powerpc-eabi-gcc $M -c exitstub_bin.s -o exitstub_bin.o
powerpc-eabi-gcc $M stub.o exitstub_bin.o forwarder.o -L$I/lib -lfat -logc -lm -Wl,--section-start,.init=0x81400000 -Wl,--section-start,.stub=0x80003400 -Wl,-Map,forwarder.map -o forwarder.elf
elf2dol forwarder.elf forwarder.dol
powerpc-eabi-size forwarder.elf
ls -la forwarder.dol
