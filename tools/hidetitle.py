"""Changes a packed WAD's title type (e.g. 00010001 -> 00010008 = hidden from the Wii Menu).

  python -I hidetitle.py in.wad out.wad 00010008

The title key in the ticket is AES-128-CBC encrypted with the common key and IV = title ID,
so it is decrypted with the old ID and encrypted again with the new one. The contents
themselves (IV = content index) do not change. The common key is read from your own
BootMii keys.bin (offset 0x114) and never written anywhere.
keys.bin path: env WS42_KEYS, default keys.bin next to this repo's root.
Sharpii cannot do this: its -id always writes 00010001.
"""
import struct
import sys

import os
KEYS = os.environ.get("WS42_KEYS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "keys.bin"))

# ---- minimal AES-128 (one block at a time is all this needs) ----
SBOX = [0] * 256
INV = [0] * 256


def _init():
    p = q = 1
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        x = (x ^ 0x63) & 0xFF
        SBOX[p] = x
        INV[x] = p
        if p == 1:
            break
    SBOX[0] = 0x63
    INV[0x63] = 0


_init()


def xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = xt(a)
        b >>= 1
    return r


def expand(key):
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = xt(rcon)
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [sum(w[r * 4:r * 4 + 4], []) for r in range(11)]


def encrypt_block(rk, b):
    s = [x ^ k for x, k in zip(b, rk[0])]
    for r in range(1, 11):
        s = [SBOX[x] for x in s]
        s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]          # ShiftRows (column-major)
        if r != 10:
            n = []
            for c in range(4):
                a = s[c * 4:c * 4 + 4]
                n += [mul(a[0], 2) ^ mul(a[1], 3) ^ a[2] ^ a[3],
                      a[0] ^ mul(a[1], 2) ^ mul(a[2], 3) ^ a[3],
                      a[0] ^ a[1] ^ mul(a[2], 2) ^ mul(a[3], 3),
                      mul(a[0], 3) ^ a[1] ^ a[2] ^ mul(a[3], 2)]
            s = n
        s = [x ^ k for x, k in zip(s, rk[r])]
    return bytes(s)


def decrypt_block(rk, b):
    s = [x ^ k for x, k in zip(b, rk[10])]
    for r in range(9, -1, -1):
        s = [s[(i - 4 * (i % 4)) % 16] for i in range(16)]          # InvShiftRows
        s = [INV[x] for x in s]
        s = [x ^ k for x, k in zip(s, rk[r])]
        if r != 0:
            n = []
            for c in range(4):
                a = s[c * 4:c * 4 + 4]
                n += [mul(a[0], 14) ^ mul(a[1], 11) ^ mul(a[2], 13) ^ mul(a[3], 9),
                      mul(a[0], 9) ^ mul(a[1], 14) ^ mul(a[2], 11) ^ mul(a[3], 13),
                      mul(a[0], 13) ^ mul(a[1], 9) ^ mul(a[2], 14) ^ mul(a[3], 11),
                      mul(a[0], 11) ^ mul(a[1], 13) ^ mul(a[2], 9) ^ mul(a[3], 14)]
            s = n
    return bytes(s)


def selftest():
    # FIPS-197 appendix C.1
    rk = expand(bytes(range(16)))
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    ct = encrypt_block(rk, pt)
    assert ct.hex() == "69c4e0d86a7b0430d8cdb78070b4c55a", ct.hex()
    assert decrypt_block(rk, ct) == pt


def align(n):
    return (n + 0x3F) & ~0x3F


def main(src, dst, newtype):
    selftest()
    wad = bytearray(open(src, "rb").read())
    hsize, typ, ver, certsz, _, tiksz, tmdsz, datasz, footsz = struct.unpack(">IHHIIIIII", wad[:0x20])
    tik = align(hsize) + align(certsz)
    tmd = tik + align(tiksz)
    old_tid = bytes(wad[tik + 0x1DC:tik + 0x1E4])
    new_tid = bytes.fromhex(newtype) + old_tid[4:]
    assert bytes(wad[tmd + 0x18C:tmd + 0x194]) == old_tid, "ticket and TMD disagree"
    common = open(KEYS, "rb").read()[0x114:0x124]
    rk = expand(common)
    enc = bytes(wad[tik + 0x1BF:tik + 0x1CF])
    iv_old = old_tid + b"\0" * 8
    iv_new = new_tid + b"\0" * 8
    key = bytes(a ^ b for a, b in zip(decrypt_block(rk, enc), iv_old))
    enc2 = encrypt_block(rk, bytes(a ^ b for a, b in zip(key, iv_new)))
    wad[tik + 0x1BF:tik + 0x1CF] = enc2
    wad[tik + 0x1DC:tik + 0x1E4] = new_tid
    wad[tmd + 0x18C:tmd + 0x194] = new_tid
    open(dst, "wb").write(wad)
    print("title", old_tid.hex(), "->", new_tid.hex())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
