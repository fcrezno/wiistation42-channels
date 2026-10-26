"""Wii channel banner (content 0) tools: U8, LZ77, IMD5, IMET, TPL.

The U8 packer writes what the Wii Menu expects (checked on 16 official channels):
  - a folder's data field = the INDEX of its parent folder (root = 0),
  - a folder's size field = the index of the first node after its subtree,
  - header size = nodes * 12 + name table (no +0x20).
Sharpii writes byte offsets into the parent field, and the Wii Menu crashed on it.
"""
import hashlib
import struct

U8_MAGIC = 0x55AA382D


# ---------------------------------------------------------------- U8

def u8_unpack(data):
    """-> dict {path: bytes} (folders are implicit)."""
    magic, root, hsize, doff = struct.unpack(">IIII", data[:16])
    assert magic == U8_MAGIC, "not a U8 archive"
    count = struct.unpack(">I", data[root + 8:root + 12])[0]
    nodes = [struct.unpack(">BxHII", data[root + i * 12:root + i * 12 + 12]) for i in range(count)]
    # type byte, then a 24-bit name offset: the ">BxH" above drops the top byte, so read it fully
    names_at = root + count * 12
    out, stack = {}, []  # stack of (end_index, path)

    def name(i):
        off = struct.unpack(">I", b"\0" + data[root + i * 12 + 1:root + i * 12 + 4])[0]
        end = data.index(b"\0", names_at + off)
        return data[names_at + off:end].decode("ascii")

    for i in range(1, count):
        while stack and i >= stack[-1][0]:
            stack.pop()
        typ, _, a, b = nodes[i]
        path = "/".join([p for _, p in stack] + [name(i)])
        if typ == 1:
            stack.append((b, name(i)))
        else:
            out[path] = data[a:a + b]
    return out


def u8_pack(files, align=0x20):
    """files: dict {path: bytes}. Folders are made from the paths, sorted like Nintendo's."""
    tree = {}
    for path, blob in files.items():
        node = tree
        parts = path.split("/")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = blob

    nodes = []  # [type, name, parent_or_offset, next_or_size, blob]

    def walk(node, parent_index):
        # keep the caller's order (u8_unpack returns Nintendo's own order)
        for key, v in node.items():
            if isinstance(v, dict):
                me = len(nodes)
                nodes.append([1, key, parent_index, 0, None])
                walk(v, me)
                nodes[me][3] = len(nodes)
            else:
                nodes.append([0, key, 0, len(v), v])

    nodes.append([1, "", 0, 0, None])
    walk(tree, 0)
    nodes[0][3] = len(nodes)

    names = b""
    name_off = []
    for n in nodes:
        name_off.append(len(names))
        names += n[1].encode("ascii") + b"\0"
    hsize = len(nodes) * 12 + len(names)
    doff = (0x20 + hsize + align - 1) // align * align
    data = bytearray()
    pos = doff
    for n in nodes:
        if n[0] == 0:
            n[2] = pos
            data += n[4]
            pad = (-len(data)) % align
            data += b"\0" * pad
            pos = doff + len(data)
    out = bytearray(struct.pack(">IIII", U8_MAGIC, 0x20, hsize, doff) + b"\0" * 16)
    for n, no in zip(nodes, name_off):
        out += struct.pack(">I", (n[0] << 24) | no) + struct.pack(">II", n[2], n[3])
    out += names
    out += b"\0" * (doff - len(out))
    last = max((n for n in nodes if n[0] == 0), key=lambda n: n[2], default=None)
    end = (last[2] - doff + last[3]) if last else 0
    out += data[:end]  # Nintendo's archives stop at the end of the last file
    return bytes(out)


# ---------------------------------------------------------------- LZ77 (type 0x10)

def lz77_decompress(data):
    assert data[0] == 0x10
    size = struct.unpack("<I", data[0:4])[0] >> 8
    out = bytearray()
    i = 4
    while len(out) < size:
        flags = data[i]; i += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> bit):
                b1, b2 = data[i], data[i + 1]; i += 2
                length = (b1 >> 4) + 3
                disp = ((b1 & 0xF) << 8 | b2) + 1
                for _ in range(length):
                    out.append(out[-disp])
            else:
                out.append(data[i]); i += 1
    return bytes(out)


def lz77_compress(data):
    """Greedy LZ77 type 0x10 with a hash of 3-byte keys (window 4096, length 3..18)."""
    out = bytearray(struct.pack("<I", (len(data) << 8) | 0x10))
    heads = {}
    i, n = 0, len(data)
    while i < n:
        flag_pos = len(out); out.append(0); flags = 0
        for bit in range(8):
            if i >= n:
                break
            best_len, best_disp = 0, 0
            key = data[i:i + 3]
            if len(key) == 3:
                for j in reversed(heads.get(key, [])[-32:]):
                    disp = i - j
                    if disp > 4096:
                        continue
                    L = 3
                    while L < 18 and i + L < n and data[j + L] == data[i + L]:
                        L += 1
                    if L > best_len:
                        best_len, best_disp = L, disp
                        if L == 18:
                            break
            step = best_len if best_len >= 3 else 1
            for k in range(i, min(i + step, n - 2)):
                heads.setdefault(data[k:k + 3], []).append(k)
            if best_len >= 3:
                flags |= 0x80 >> bit
                d = best_disp - 1
                out += bytes([((best_len - 3) << 4) | (d >> 8), d & 0xFF])
                i += best_len
            else:
                out.append(data[i]); i += 1
        out[flag_pos] = flags
    while len(out) % 4:
        out.append(0)
    return bytes(out)


# ---------------------------------------------------------------- IMD5 (icon.bin, banner.bin)

def imd5_unwrap(data):
    assert data[:4] == b"IMD5"
    body = data[0x20:]
    return lz77_decompress(body[4:]) if body[:4] == b"LZ77" else body


def imd5_wrap(u8, compress=True):
    body = (b"LZ77" + lz77_compress(u8)) if compress else u8
    return b"IMD5" + struct.pack(">I", len(body)) + b"\0" * 8 + hashlib.md5(body).digest() + body


# ---------------------------------------------------------------- IMET (content 0)

def imet_unpack(app):
    assert app[0x80:0x84] == b"IMET", "IMET not at 0x80"
    return u8_unpack(app[0x640:])


def imet_pack(arc_files, title, icon_u8_size, banner_u8_size, langs=7):
    """arc_files: {"meta/icon.bin":..., "meta/banner.bin":..., "meta/sound.bin":...}
    The IMET sizes are the UNCOMPRESSED U8 sizes of icon and banner (base: 33,856 / 555,328)."""
    arc = u8_pack(arc_files)
    head = bytearray(0x640)
    head[0x80:0x84] = b"IMET"
    struct.pack_into(">II", head, 0x84, 0x600, 3)
    struct.pack_into(">IIII", head, 0x8C, icon_u8_size, banner_u8_size,
                     len(arc_files["meta/sound.bin"]), 0)
    # language slots of 0x54 bytes (42 UTF-16 chars) from 0x9C; the base fills seven
    t = title.encode("utf-16-be")[:0x52]
    for lang in range(langs):
        o = 0x9C + lang * 0x54
        head[o:o + len(t)] = t
    md5 = hashlib.md5(bytes(head[0x40:0x630]) + b"\0" * 16).digest()
    head[0x630:0x640] = md5
    return bytes(head) + arc


# ---------------------------------------------------------------- TPL (RGB565, one image)

def tpl_info(tpl):
    count = struct.unpack(">I", tpl[4:8])[0]
    img_off = struct.unpack(">I", tpl[12:16])[0]
    h, w, fmt, data_off = struct.unpack(">HHII", tpl[img_off:img_off + 12])
    return count, w, h, fmt, data_off


def rgb565_tpl_replace(tpl, image):
    """Replace the pixels of a one-image RGB565 TPL; size must match."""
    count, w, h, fmt, data_off = tpl_info(tpl)
    assert fmt == 4, "expected RGB565 (format 4), got %d" % fmt
    img = image.convert("RGB")
    assert img.size == (w, h), "art is %s, TPL wants %dx%d" % (img.size, w, h)
    px = img.load()
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            for y in range(by, by + 4):
                for x in range(bx, bx + 4):
                    if x < w and y < h:
                        r, g, b = px[x, y]
                    else:
                        r = g = b = 0
                    out += struct.pack(">H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    tpl = bytearray(tpl)
    tpl[data_off:data_off + len(out)] = out
    return bytes(tpl)


# ---------------------------------------------------------------- TPL decode/encode (I4, I8, IA4, IA8, RGB565, RGB5A3)

TPL_BLOCK = {0: (8, 8, 4), 1: (8, 4, 8), 2: (8, 4, 8), 3: (4, 4, 16), 4: (4, 4, 16), 5: (4, 4, 16)}


def _px_decode(fmt, raw):
    """raw: one texel's bits as an int -> (r, g, b, a)"""
    if fmt == 0:
        v = raw * 17
        return v, v, v, 255
    if fmt == 1:
        return raw, raw, raw, 255
    if fmt == 2:
        a, i = (raw >> 4) * 17, (raw & 15) * 17
        return i, i, i, a
    if fmt == 3:
        a, i = raw >> 8, raw & 255
        return i, i, i, a
    if fmt == 4:
        r, g, b = (raw >> 11) & 31, (raw >> 5) & 63, raw & 31
        return r * 255 // 31, g * 255 // 63, b * 255 // 31, 255
    if fmt == 5:
        if raw & 0x8000:
            r, g, b = (raw >> 10) & 31, (raw >> 5) & 31, raw & 31
            return r * 255 // 31, g * 255 // 31, b * 255 // 31, 255
        a = ((raw >> 12) & 7) * 255 // 7
        return ((raw >> 8) & 15) * 17, ((raw >> 4) & 15) * 17, (raw & 15) * 17, a
    raise ValueError("format %d" % fmt)


def _px_encode(fmt, rgba):
    r, g, b, a = rgba
    i = (r * 77 + g * 150 + b * 29) >> 8
    if fmt == 0:
        return i >> 4
    if fmt == 1:
        return i
    if fmt == 2:
        return ((a >> 4) << 4) | (i >> 4)
    if fmt == 3:
        return (a << 8) | i
    if fmt == 4:
        return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    if fmt == 5:
        if a >= 0xE0:
            return 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
        return ((a >> 5) << 12) | ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)
    raise ValueError("format %d" % fmt)


def tpl_decode(tpl):
    from PIL import Image
    count, w, h, fmt, off = tpl_info(tpl)
    bw, bh, bpp = TPL_BLOCK[fmt]
    img = Image.new("RGBA", (w, h))
    px = img.load()
    bits = int.from_bytes(tpl[off:], "big")
    total = (len(tpl) - off) * 8
    pos = 0
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            for y in range(by, by + bh):
                for x in range(bx, bx + bw):
                    raw = (bits >> (total - pos - bpp)) & ((1 << bpp) - 1)
                    pos += bpp
                    if x < w and y < h:
                        px[x, y] = _px_decode(fmt, raw)
    return img


def tpl_replace(tpl, image):
    """Replace the pixels of a one-image TPL in its own format; size must match."""
    count, w, h, fmt, off = tpl_info(tpl)
    img = image.convert("RGBA")
    assert img.size == (w, h), "art is %s, TPL wants %dx%d" % (img.size, w, h)
    bw, bh, bpp = TPL_BLOCK[fmt]
    px = img.load()
    acc, nbits, out = 0, 0, bytearray()
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            for y in range(by, by + bh):
                for x in range(bx, bx + bw):
                    v = _px_encode(fmt, px[x, y] if x < w and y < h else (0, 0, 0, 0))
                    acc = (acc << bpp) | v
                    nbits += bpp
                    while nbits >= 8:
                        nbits -= 8
                        out.append((acc >> nbits) & 255)
    tpl = bytearray(tpl)
    tpl[off:off + len(out)] = out
    return bytes(tpl)
