"""Extracts your own BootMii NAND backup (nand.bin + keys.bin) into a Dolphin "Wii" folder,
so Dolphin can run your own Wii Menu. Read-only on the backup. Windows only (AES from bcrypt.dll).

  python -I nandextract.py <out Wii folder> [nand.bin] [keys.bin]

nand.bin: 4096 blocks x 64 pages x (0x800 data + 0x40 spare) = 553,649,152 bytes.
A cluster = 8 pages = 0x4000 bytes. SFFS superblocks fill the last 0x100 clusters (16 each);
the newest one (highest generation) holds the FAT (u16 per cluster) and the FST (0x20-byte entries).
File clusters are AES-128-CBC encrypted with the NAND key (keys.bin 0x158), IV = 0, per cluster.
AES comes from Windows CNG (bcrypt.dll) through ctypes: nothing to install.
"""
import ctypes
import os
import struct
import sys
from ctypes import wintypes

NAND = sys.argv[2] if len(sys.argv) > 2 else "nand.bin"
KEYS = sys.argv[3] if len(sys.argv) > 3 else "keys.bin"
PAGE, SPARE = 0x800, 0x40
CLUSTER = 8 * PAGE

bcrypt = ctypes.WinDLL("bcrypt")


class Aes:
    def __init__(self, key):
        self.alg = wintypes.HANDLE()
        assert bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(self.alg), "AES", None, 0) == 0
        mode = "ChainingModeCBC".encode("utf-16-le") + b"\0\0"
        assert bcrypt.BCryptSetProperty(self.alg, "ChainingMode", mode, len(mode), 0) == 0
        self.key = wintypes.HANDLE()
        kb = ctypes.create_string_buffer(key)
        assert bcrypt.BCryptGenerateSymmetricKey(self.alg, ctypes.byref(self.key), None, 0, kb, 16, 0) == 0

    def decrypt(self, data, iv=b"\0" * 16):
        out = ctypes.create_string_buffer(len(data))
        n = wintypes.ULONG()
        ivb = ctypes.create_string_buffer(iv, 16)
        r = bcrypt.BCryptDecrypt(self.key, data, len(data), None, ivb, 16, out, len(data), ctypes.byref(n), 0)
        assert r == 0, hex(r & 0xFFFFFFFF)
        return out.raw[:n.value]


def main(outdir):
    nand_key = open(KEYS, "rb").read()[0x158:0x168]
    aes = Aes(nand_key)
    f = open(NAND, "rb")

    def cluster(c, decrypt=True):
        f.seek(c * 8 * (PAGE + SPARE))
        raw = f.read(8 * (PAGE + SPARE))
        data = b"".join(raw[i * (PAGE + SPARE):i * (PAGE + SPARE) + PAGE] for i in range(8))
        return aes.decrypt(data) if decrypt else data

    best, best_gen = None, -1
    for sb in range(16):
        c0 = 0x7F00 + sb * 16
        head = cluster(c0, False)[:8]
        if head[:4] == b"SFFS":
            gen = struct.unpack(">I", head[4:8])[0]
            if gen > best_gen:
                best, best_gen = c0, gen
    assert best is not None, "no SFFS superblock"
    sb = b"".join(cluster(best + i, False) for i in range(16))
    fat = struct.unpack(">32768H", sb[0x0C:0x0C + 0x10000])
    fst_at = 0x0C + 0x10000

    def entry(i):
        e = sb[fst_at + i * 0x20:fst_at + i * 0x20 + 0x20]
        name = e[:12].split(b"\0")[0].decode("ascii", "replace")
        mode, attr, sub, sib, size, uid, gid = struct.unpack(">BBHHIIH", e[12:28])
        return name, mode, sub, sib, size

    count = [0, 0]

    def walk(i, path):
        while i != 0xFFFF:
            name, mode, sub, sib, size = entry(i)
            p = os.path.join(path, name) if name != "/" else path
            if mode & 3 == 2:
                os.makedirs(p, exist_ok=True)
                if sub != 0xFFFF:
                    walk(sub, p)
            elif mode & 3 == 1:
                data = bytearray()
                c = sub
                while c < 0xFFF0 and len(data) < size:
                    data += cluster(c)
                    c = fat[c]
                with open(p, "wb") as o:
                    o.write(bytes(data[:size]))
                count[0] += 1
                count[1] += size
            i = sib

    name, mode, sub, sib, size = entry(0)
    os.makedirs(outdir, exist_ok=True)
    walk(sub, outdir)
    print("superblock gen", best_gen, "files", count[0], "bytes", count[1])


if __name__ == "__main__":
    main(sys.argv[1])
