"""Repacks a GameCube memory card image (.raw) into a smaller card size, moving every save
into contiguous blocks. Read-only on the source. For example: fit a 507-block card
with fewer than 251 blocks used into Nintendont's standard 251-block card.

  python -I gccard_repack.py <in.raw> <out.raw> <blocks: 59|123|251|507|1019|2043>

Card layout (blocks of 0x2000): 0 header, 1-2 directory (two copies), 3-4 block table
(BAT, two copies), 5.. data. Checksums: two u16 sums over big-endian u16 words (the plain
sum and the sum of inverted words; 0xFFFF becomes 0), the same way Dolphin computes them.
"""
import struct
import sys

B = 0x2000
SIZES = {59: 4, 123: 8, 251: 16, 507: 32, 1019: 64, 2043: 128}   # blocks -> Mbit


def checksums(data):
    c1 = c2 = 0
    for (w,) in struct.iter_unpack(">H", data):
        c1 = (c1 + w) & 0xFFFF
        c2 = (c2 + (w ^ 0xFFFF)) & 0xFFFF
    if c1 == 0xFFFF:
        c1 = 0
    if c2 == 0xFFFF:
        c2 = 0
    return c1, c2


def newest(a, b, counter):
    return a if counter(a) >= counter(b) else b


def read(src):
    d = open(src, "rb").read()
    D = newest(d[B:2 * B], d[2 * B:3 * B], lambda x: struct.unpack(">H", x[0x1FFA:0x1FFC])[0])
    T = newest(d[3 * B:4 * B], d[4 * B:5 * B], lambda x: struct.unpack(">H", x[4:6])[0])
    return d, D, T


def chain(T, first):
    out, b = [], first
    while True:
        out.append(b)
        nxt = struct.unpack(">H", T[0xA + (b - 5) * 2:0xC + (b - 5) * 2])[0]
        if nxt == 0xFFFF:
            return out
        b = nxt


def verify(path):
    """Checks every checksum and every file chain; returns a list of problems (empty = good)."""
    d, _, _ = read(path)
    probs = []
    mbit = struct.unpack(">H", d[0x22:0x24])[0]
    blocks = mbit * 16 - 5
    if len(d) != mbit * 0x20000:
        probs.append("file size %d does not match %d Mbit" % (len(d), mbit))
    if checksums(d[0:0x1FC]) != struct.unpack(">HH", d[0x1FC:0x200]):
        probs.append("header checksum")
    for i, base in ((1, B), (2, 2 * B)):
        if checksums(d[base:base + 0x1FFC]) != struct.unpack(">HH", d[base + 0x1FFC:base + 0x2000]):
            probs.append("directory %d checksum" % i)
    for i, base in ((1, 3 * B), (2, 4 * B)):
        if checksums(d[base + 4:base + B]) != struct.unpack(">HH", d[base:base + 4]):
            probs.append("block table %d checksum" % i)
    _, D, T = read(path)
    used = 0
    for i in range(127):
        e = D[i * 0x40:(i + 1) * 0x40]
        if e[:4] == b"\xff" * 4:
            continue
        first, n = struct.unpack(">HH", e[0x36:0x3A])
        c = chain(T, first)
        used += len(c)
        if len(c) != n:
            probs.append("file %d chain %d blocks, entry says %d" % (i, len(c), n))
        if max(c) >= blocks + 5:
            probs.append("file %d past the end of the card" % i)
    free = struct.unpack(">H", T[6:8])[0]
    if free != blocks - used:
        probs.append("free count %d, expected %d" % (free, blocks - used))
    return probs


def repack(src, dst, blocks):
    d, D, T = read(src)
    mbit = SIZES[blocks]
    out = bytearray(b"\0" * (mbit * 0x20000))
    # header: same card identity, new size, new checksums
    hdr = bytearray(d[0:B])
    struct.pack_into(">H", hdr, 0x22, mbit)
    struct.pack_into(">HH", hdr, 0x1FC, *checksums(hdr[0:0x1FC]))
    out[0:B] = hdr
    newdir = bytearray(D)
    bat = bytearray(b"\0" * B)
    nxt_free = 5
    for i in range(127):
        e = D[i * 0x40:(i + 1) * 0x40]
        if e[:4] == b"\xff" * 4:
            continue
        old = chain(T, struct.unpack(">H", e[0x36:0x38])[0])
        new = list(range(nxt_free, nxt_free + len(old)))
        if new[-1] >= blocks + 5:
            raise SystemExit("the saves do not fit in %d blocks" % blocks)
        for o, n in zip(old, new):
            out[n * B:(n + 1) * B] = d[o * B:(o + 1) * B]
        for k, n in enumerate(new):
            struct.pack_into(">H", bat, 0xA + (n - 5) * 2, new[k + 1] if k + 1 < len(new) else 0xFFFF)
        struct.pack_into(">H", newdir, i * 0x40 + 0x36, new[0])
        nxt_free += len(old)
    used = nxt_free - 5
    struct.pack_into(">H", newdir, 0x1FFA, struct.unpack(">H", D[0x1FFA:0x1FFC])[0] + 1)
    struct.pack_into(">HH", newdir, 0x1FFC, *checksums(newdir[0:0x1FFC]))
    struct.pack_into(">HHH", bat, 4, struct.unpack(">H", T[4:6])[0] + 1, blocks - used, nxt_free - 1)
    struct.pack_into(">HH", bat, 0, *checksums(bat[4:B]))
    out[B:2 * B] = newdir
    out[2 * B:3 * B] = newdir
    out[3 * B:4 * B] = bat
    out[4 * B:5 * B] = bat
    open(dst, "wb").write(out)
    return used


if __name__ == "__main__":
    src, dst, blocks = sys.argv[1], sys.argv[2], int(sys.argv[3])
    p = verify(src)
    print("source checks:", "OK" if not p else p)
    used = repack(src, dst, blocks)
    p = verify(dst)
    print("repacked %d used blocks into a %d-block card: %s" % (used, blocks, "OK" if not p else p))
