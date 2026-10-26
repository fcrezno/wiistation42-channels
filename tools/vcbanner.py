"""Virtual Console-style banner (content 0) built the GC-VC way: from a REAL SNES Virtual Console
banner that you own (tested with Super Mario RPG, title 00010001-JCBE), with the pictures swapped
and the layout text edited. The text is drawn by the Wii itself in its system font (wbf1.brfna).

Donor parts (put in donor/ by tools/setup_donor.py):
  banner: arc/blyt/banner.brlyt (texts), arc/timg/VCPic.tpl 256x192 RGB565 (title screen),
          arc/timg/my_BackSNES_a.tpl 256x128 I4 (console logo in the background)
  icon:   arc/timg/IconVCPic.tpl 128x96 RGB565 (title screen), arc/timg/LogoSNES.tpl 112x32 RGB5A3
  sound.bin (the VC banner sound)
"""
import os
import struct

from PIL import Image, ImageDraw, ImageFont

import wiibanner as wb

HERE = os.path.dirname(os.path.abspath(__file__))
DONOR = os.path.join(os.path.dirname(HERE), "donor")


# ---------------------------------------------------------------- BRLYT text

def brlyt_set_texts(brlyt, texts):
    """texts: {pane name: str}. Rebuilds each named txt1 section with the new string."""
    out = bytearray(brlyt[:0x10])
    n = struct.unpack(">H", brlyt[0x0E:0x10])[0]
    off = struct.unpack(">H", brlyt[0x0C:0x0E])[0]
    out[len(out):] = brlyt[0x10:off]
    done = set()
    for _ in range(n):
        magic = brlyt[off:off + 4]
        size = struct.unpack(">I", brlyt[off + 4:off + 8])[0]
        sec = bytearray(brlyt[off:off + size])
        if magic == b"txt1":
            name = sec[0x0C:0x1C].split(b"\0")[0].decode()
            if name in texts:
                toff = struct.unpack(">I", sec[0x58:0x5C])[0]
                assert toff == 0x74
                s = texts[name].encode("utf-16-be") + b"\0\0"
                body = sec[:0x74] + s
                body += b"\0" * ((-len(body)) % 4)
                struct.pack_into(">HH", body, 0x4C, len(s), len(s))
                struct.pack_into(">I", body, 4, len(body))
                sec = body
                done.add(name)
        out += sec
        off += size
    missing = set(texts) - done
    assert not missing, "no such text panes: %s" % missing
    struct.pack_into(">I", out, 8, len(out))
    return bytes(out)


# ---------------------------------------------------------------- console logos

def _text(d, xy, s, fnt, fill, anchor="mm"):
    d.text(xy, s, font=fnt, fill=fill, anchor=anchor)


LOGOS = os.path.join(os.path.dirname(HERE), "art", "logos")


def _official(name, colour):
    """An official logo (art/logos, from Wikimedia Commons) as one flat colour: its alpha is the shape."""
    src = Image.open(os.path.join(LOGOS, name)).convert("RGBA")
    out = Image.new("RGBA", src.size, colour + (0,))
    out.putalpha(src.split()[3])
    return out


def _official_gc(colour):
    """The official NINTENDO GAMECUBE logo (Wikimedia Commons, public domain; black on transparent),
    recoloured: its alpha is the shape."""
    src = Image.open(os.path.join(LOGOS, "gc_official.png")).convert("RGBA")
    alpha = src.split()[3]
    out = Image.new("RGBA", src.size, colour + (0,))
    out.putalpha(alpha)
    return out


# system -> (logo file in art/logos, tile colour). Colour None = the logo's own colours.
# Logos are NOT in this repo: put your own PNGs (transparent background) in art/logos with these
# names (see README). A missing logo keeps the donor's SNES logo.
SYSTEM_LOGOS = {
    "NINTENDO GAMECUBE": ("gc_official.png", (84, 66, 160)),
    "GAME BOY COLOR": ("gbc_official.png", None),
    "GAME BOY ADVANCE": ("gba_official.png", None),
    "NINTENDO ENTERTAINMENT SYSTEM": ("nes_official.png", None),
    "SEGA GENESIS": ("genesis_official.png", None),
    "MASTER SYSTEM": ("sms_official.png", None),
    "GAME GEAR": ("gg_official.png", None),
    "NINTENDO 64": ("n64_official.png", None),
    "PLAYSTATION": ("psx_wordmark.png", (40, 40, 40)),
}


LUMA_LOGOS = {"nes_official.png", "genesis_official.png", "gba_official.png"}


def _fit(img, w, h):
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def back_logo(system):
    """256x128 I4 background logo (white on black, like the SNES one): None keeps the donor's SNES logo."""
    if system not in SYSTEM_LOGOS or not os.path.exists(os.path.join(LOGOS, SYSTEM_LOGOS[system][0])):
        return None
    img = Image.new("RGBA", (256, 128), (0, 0, 0, 255))
    name = SYSTEM_LOGOS[system][0]
    if name in LUMA_LOGOS:
        # logos with filled boxes (NES, Genesis, GBA): keep their light/dark detail as grey levels
        src = Image.open(os.path.join(LOGOS, name)).convert("RGBA")
        grey = src.convert("L").point(lambda v: min(255, 60 + v))
        logo = Image.merge("RGBA", (grey, grey, grey, src.split()[3]))
        logo = _fit(logo, 232, 64)
    else:
        logo = _fit(_official(name, (255, 255, 255)), 232, 64)
    img.alpha_composite(logo, ((256 - logo.width) // 2, 6))
    return img


def icon_logo(system):
    """112x32 RGB5A3 tile logo (transparent, white halo): None keeps the donor's SNES logo."""
    if system not in SYSTEM_LOGOS or not os.path.exists(os.path.join(LOGOS, SYSTEM_LOGOS[system][0])):
        return None
    name, colour = SYSTEM_LOGOS[system]
    img = Image.new("RGBA", (112, 32), (0, 0, 0, 0))
    src = _official(name, colour) if colour else Image.open(os.path.join(LOGOS, name)).convert("RGBA")
    logo = _fit(src, 108, 30)
    halo = _fit(_official(name, (255, 255, 255)), 108, 30)
    x, y = (112 - logo.width) // 2, (32 - logo.height) // 2
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        img.alpha_composite(halo, (x + dx, y + dy))
    img.alpha_composite(logo, (x, y))
    return img


# ---------------------------------------------------------------- the banner

def title_lines(title, width=24):
    """VC titles break onto a second line, usually after a colon."""
    if len(title) <= width:
        return title
    if ": " in title:
        a, b = title.split(": ", 1)
        return a + ":\n" + b
    words, lines, cur = title.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    return "\n".join(lines[:2])


def screen_fit(shot, w, h, system):
    """Title screen to w x h. A Game Boy screen (10:9) keeps its shape with black bars;
    TV consoles fill the 4:3 frame like real VC pictures. Small pixel art scales sharp first."""
    pic = shot.convert("RGB")
    if pic.width < 300:
        k = max(1, -(-h // pic.height))
        pic = pic.resize((pic.width * k, pic.height * k), Image.NEAREST)
    if system == "GAME BOY COLOR":
        s = h / pic.height
        inner = pic.resize((round(pic.width * s), h), Image.LANCZOS)
        out = Image.new("RGB", (w, h), (0, 0, 0))
        out.paste(inner, ((w - inner.width) // 2, 0))
        return out
    return pic.resize((w, h), Image.LANCZOS)


def read_donor(part):
    base = os.path.join(DONOR, part)
    files = {}
    for root, _, names in os.walk(base):
        for n in names:
            if n.endswith(".png"):
                continue
            p = os.path.join(root, n)
            files[os.path.relpath(p, base).replace("\\", "/")] = open(p, "rb").read()
    return files


ORDER_BANNER = ["arc/anim/banner_Loop.brlan", "arc/anim/banner_Start.brlan", "arc/blyt/banner.brlyt",
                "arc/timg/my_BackSNES_a.tpl", "arc/timg/my_Beta16x16_a.tpl", "arc/timg/my_Grad_b.tpl",
                "arc/timg/my_Shade_a.tpl", "arc/timg/my_TVW_a.tpl", "arc/timg/my_VCLine_e.tpl", "arc/timg/VCPic.tpl"]
ORDER_ICON = ["arc/anim/icon.brlan", "arc/blyt/icon.brlyt", "arc/timg/Back_a.tpl", "arc/timg/IconVCPic.tpl",
              "arc/timg/LogoSNES.tpl"]


def ordered(files, order):
    """Nintendo's node order (the donor's): folders anim, blyt, timg, files as listed."""
    assert set(files) == set(order), set(files) ^ set(order)
    return {k: files[k] for k in order}


def build(game, shot, save_png=None):
    """game: games.json entry (title, system, year, players, esrb). shot: title-screen PIL image."""
    banner = read_donor("banner")
    icon = read_donor("icon")
    year, players, esrb = str(game["year"]), str(game["players"]), game.get("esrb", "")
    pf = game["system"] if game["system"] in SYSTEM_LOGOS else "SUPER NINTENDO ENTERTAINMENT SYSTEM"
    title = title_lines(game.get("vc_title", game["title"]))
    esrb_fr = {"Everyone": "Enfants et adultes", "Teen": "Adolescents"}.get(esrb, esrb)
    banner["arc/blyt/banner.brlyt"] = brlyt_set_texts(banner["arc/blyt/banner.brlyt"], {
        "T_VCTitle_ENG": title, "T_VCTitle_FRA": title, "T_VCTitle_SPA": title,
        "T_Year_ENG": "Released: " + year, "T_Year_FRA": "Publi\u00e9 en " + year, "T_Year_SPA": "A\u00f1o: " + year,
        "T_Play_ENG": "Players: " + players, "T_Play_FRA": "Joueurs: " + players,
        "T_Play_SPA": "Jugadores: " + players,
        "T_PF": pf,
        "T_ESRB_ENG": ("ESRB Rating: " + esrb + "\n") if esrb else "\n",
        "T_ESRB_FRA": ("Classement ESRB: " + esrb_fr + "\n") if esrb else "\n",
    })
    vc = screen_fit(shot, 256, 192, game["system"])
    ic = screen_fit(shot, 128, 96, game["system"])
    banner["arc/timg/VCPic.tpl"] = wb.tpl_replace(banner["arc/timg/VCPic.tpl"], vc)
    icon["arc/timg/IconVCPic.tpl"] = wb.tpl_replace(icon["arc/timg/IconVCPic.tpl"], ic)
    bl = back_logo(game["system"])
    if bl is not None:
        banner["arc/timg/my_BackSNES_a.tpl"] = wb.tpl_replace(banner["arc/timg/my_BackSNES_a.tpl"], bl)
    il = icon_logo(game["system"])
    if il is not None:
        icon["arc/timg/LogoSNES.tpl"] = wb.tpl_replace(icon["arc/timg/LogoSNES.tpl"], il)
    if save_png:
        for name, b in (("vcpic", banner["arc/timg/VCPic.tpl"]), ("back", banner["arc/timg/my_BackSNES_a.tpl"]),
                        ("iconpic", icon["arc/timg/IconVCPic.tpl"]), ("logo", icon["arc/timg/LogoSNES.tpl"])):
            wb.tpl_decode(b).save(save_png + "_" + name + ".png")
    bu8 = wb.u8_pack(ordered(banner, ORDER_BANNER))
    iu8 = wb.u8_pack(ordered(icon, ORDER_ICON))
    arc = {"meta/banner.bin": wb.imd5_wrap(bu8), "meta/icon.bin": wb.imd5_wrap(iu8),
           "meta/sound.bin": open(os.path.join(DONOR, "sound.bin"), "rb").read()}
    return wb.imet_pack(arc, game["title"][:40], len(iu8), len(bu8))
