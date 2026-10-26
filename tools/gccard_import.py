"""Copies one save (directory entry + its blocks) from one GameCube card image (.raw) into another,
replacing the save with the same game code and file name. Read-only on the source; writes a NEW
output file (never the destination in place). For example: move a save from a real memory card (GCMM raw backup) into
Nintendont's emulated card. NOT yet tested on hardware: keep a backup of both cards.

  python -I gccard_import.py <from.raw> <into.raw> <out.raw> <GAMECODE> [file name]

Card layout and checksums: see gccard_repack.py.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gccard_repack as g  # noqa: E402

B = g.B


def entries(D):
    for i in range(127):
        e = D[i * 0x40:(i + 1) * 0x40]
        if e[:4] != b"\xff" * 4:
            yield i, e


def name_of(e):
    return e[8:40].split(b"\0")[0].decode("ascii", "replace")


def main(src, dst, out, code, fname=None):
    sd, sD, sT = g.read(src)
    dd, dD, dT = g.read(dst)
    picks = [(i, e) for i, e in entries(sD) if e[:6].decode("ascii", "replace").startswith(code)
             and (fname is None or name_of(e) == fname)]
    if len(picks) != 1:
        raise SystemExit("need exactly one matching save in the source, found %d: %s"
                         % (len(picks), [name_of(e) for _, e in picks]))
    _, se = picks[0]
    sblocks = g.chain(sT, struct.unpack(">H", se[0x36:0x38])[0])
    data = [sd[b * B:(b + 1) * B] for b in sblocks]

    out_img = bytearray(dd)
    newdir = bytearray(dD)
    bat = bytearray(dT)
    mbit = struct.unpack(">H", dd[0x22:0x24])[0]
    total = mbit * 16 - 5

    # free the old copy (same game code + name), if there is one
    slot = None
    for i, e in entries(dD):
        if e[:6] == se[:6] and name_of(e) == name_of(se):
            for b in g.chain(dT, struct.unpack(">H", e[0x36:0x38])[0]):
                struct.pack_into(">H", bat, 0xA + (b - 5) * 2, 0)
            newdir[i * 0x40:(i + 1) * 0x40] = b"\xff" * 0x40
            slot = i
    if slot is None:
        slot = next((i for i in range(127) if newdir[i * 0x40:i * 0x40 + 4] == b"\xff" * 4), None)
        if slot is None:
            raise SystemExit("the destination card has no free directory entry")

    free = [b for b in range(5, total + 5) if struct.unpack(">H", bat[0xA + (b - 5) * 2:0xC + (b - 5) * 2])[0] == 0]
    if len(free) < len(data):
        raise SystemExit("not enough free blocks: need %d, have %d" % (len(data), len(free)))
    new = free[:len(data)]
    for k, (n, blk) in enumerate(zip(new, data)):
        out_img[n * B:(n + 1) * B] = blk
        struct.pack_into(">H", bat, 0xA + (n - 5) * 2, new[k + 1] if k + 1 < len(new) else 0xFFFF)
    e = bytearray(se)
    struct.pack_into(">H", e, 0x36, new[0])
    newdir[slot * 0x40:(slot + 1) * 0x40] = e

    used = sum(1 for b in range(5, total + 5) if struct.unpack(">H", bat[0xA + (b - 5) * 2:0xC + (b - 5) * 2])[0])
    struct.pack_into(">H", newdir, 0x1FFA, (struct.unpack(">H", dD[0x1FFA:0x1FFC])[0] + 1) & 0xFFFF)
    struct.pack_into(">HH", newdir, 0x1FFC, *g.checksums(newdir[0:0x1FFC]))
    struct.pack_into(">HHH", bat, 4, (struct.unpack(">H", dT[4:6])[0] + 1) & 0xFFFF, total - used, new[-1])
    struct.pack_into(">HH", bat, 0, *g.checksums(bat[4:B]))
    for base in (B, 2 * B):
        out_img[base:base + B] = newdir
    for base in (3 * B, 4 * B):
        out_img[base:base + B] = bat
    open(out, "wb").write(out_img)
    print("imported %s %r (%d blocks) into slot %d" % (se[:6].decode(), name_of(se), len(data), slot))
    p = g.verify(out)
    print("output checks:", "OK" if not p else p)


if __name__ == "__main__":
    main(*sys.argv[1:6])
