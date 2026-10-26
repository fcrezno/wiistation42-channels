"""Reads the GameCube disc banner (opening.bnr: 96x32 RGB5A3 picture) from your own
ISO or CISO, read-only.

  python -I gcbanner.py <game.iso|game.ciso> <out.png>
"""
import struct
import sys

from PIL import Image


class Disc:
    def __init__(self, path):
        self.f = open(path, "rb")
        head = self.f.read(8)
        self.ciso = head[:4] == b"CISO"
        if self.ciso:
            self.block = struct.unpack("<I", head[4:8])[0]
            used = self.f.read(0x8000 - 8)
            self.where = {}
            n = 0
            for i, b in enumerate(used):
                if b:
                    self.where[i] = n
                    n += 1

    def read(self, off, size):
        if not self.ciso:
            self.f.seek(off)
            return self.f.read(size)
        out = b""
        while size:
            blk, inner = divmod(off, self.block)
            take = min(size, self.block - inner)
            if blk in self.where:
                self.f.seek(0x8000 + self.where[blk] * self.block + inner)
                out += self.f.read(take)
            else:
                out += b"\0" * take
            off += take
            size -= take
        return out


def find_root_file(disc, name):
    fst_off, fst_size = struct.unpack(">II", disc.read(0x424, 8))
    fst = disc.read(fst_off, fst_size)
    count = struct.unpack(">I", fst[8:12])[0]
    names = count * 12
    for i in range(1, count):
        w0, off, size = struct.unpack(">III", fst[i * 12:i * 12 + 12])
        if w0 >> 24:
            continue
        n0 = names + (w0 & 0xFFFFFF)
        nm = fst[n0:fst.index(b"\0", n0)].decode("ascii", "replace")
        if nm.lower() == name:
            return off, size
    raise FileNotFoundError(name)


def banner_image(path):
    disc = Disc(path)
    off, size = find_root_file(disc, "opening.bnr")
    bnr = disc.read(off, size)
    assert bnr[:3] == b"BNR", bnr[:4]
    px = bnr[0x20:0x20 + 96 * 32 * 2]
    img = Image.new("RGBA", (96, 32))
    p = img.load()
    i = 0
    for by in range(0, 32, 4):
        for bx in range(0, 96, 4):
            for y in range(by, by + 4):
                for x in range(bx, bx + 4):
                    v = struct.unpack(">H", px[i:i + 2])[0]
                    i += 2
                    if v & 0x8000:
                        r, g, b, a = (v >> 10) & 31, (v >> 5) & 31, v & 31, 255
                        r, g, b = r * 255 // 31, g * 255 // 31, b * 255 // 31
                    else:
                        a = ((v >> 12) & 7) * 255 // 7
                        r, g, b = ((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17
                    p[x, y] = (r, g, b, a)
    return img


if __name__ == "__main__":
    banner_image(sys.argv[1]).save(sys.argv[2])
