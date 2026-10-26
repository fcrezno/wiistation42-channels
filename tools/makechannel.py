"""Makes one Wii Menu game channel (a WAD) from games.json.

  python -I makechannel.py <key>      e.g. pikmin, chrono

The WAD has two contents:
  0  banner: a Virtual Console-style banner (vcbanner.py) made from YOUR OWN SNES VC banner in donor/,
     with the game's title screen and texts
  1  forwarder.dol (boot), with the game's start values written into its cfg block

TMD: IOS58, access rights 3 (AHBPROT + DVD; Nintendont needs AHBPROT), boot index 1.
Sharpii packs and encrypts: WAD -p -id XXXX -ios 58 -f
(never -title: it repacks the banner with the U8 parent bug).

Needs (none of them are in this repo): donor/ (setup_donor.py), base/ (setup_base.py),
Sharpii.exe in tools/ (or WS42_SHARPII), a title screen PNG per game, and for GameCube games
your own nincfg.bin from Nintendont.
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vcbanner  # noqa: E402

BASE = os.path.join(ROOT, "base")
SHARPII = os.environ.get("WS42_SHARPII", os.path.join(HERE, "Sharpii.exe"))
FWD = os.path.join(ROOT, "forwarder", "forwarder.dol")


def root_path(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def build_banner_from(game):
    """Keeps an existing banner (the decrypted content 0 of a channel you made or own), repacked
    cleanly with the new title. icon_art (optional): a 128x96 picture for the Wii Menu tile."""
    old = vcbanner.wb.imet_unpack(open(root_path(game["banner_from"]), "rb").read())
    arc, sizes = {}, {}
    for part in ("banner", "icon"):
        files = vcbanner.wb.u8_unpack(vcbanner.wb.imd5_unwrap(old["meta/%s.bin" % part]))
        if part == "icon" and game.get("icon_art"):
            if "arc/timg/icon.tpl" not in files:
                raise SystemExit("icon_art needs a banner with arc/timg/icon.tpl (170x96 RGB565)")
            # the Wii Menu shows only the middle ~128 px of the 170 px tile picture:
            # the 128x96 art goes in the middle, its edge columns are stretched out to the sides
            a = Image.open(root_path(game["icon_art"])).convert("RGB").resize((128, 96), Image.LANCZOS)
            t = Image.new("RGB", (170, 96))
            t.paste(a.crop((0, 0, 1, 96)).resize((21, 96)), (0, 0))
            t.paste(a, (21, 0))
            t.paste(a.crop((127, 0, 128, 96)).resize((21, 96)), (149, 0))
            files["arc/timg/icon.tpl"] = vcbanner.wb.rgb565_tpl_replace(files["arc/timg/icon.tpl"], t)
        u8 = vcbanner.wb.u8_pack(files)
        sizes[part] = len(u8)
        arc["meta/%s.bin" % part] = vcbanner.wb.imd5_wrap(u8)
    arc["meta/sound.bin"] = old["meta/sound.bin"]
    arc = {k: arc[k] for k in ("meta/banner.bin", "meta/icon.bin", "meta/sound.bin")}
    return vcbanner.wb.imet_pack(arc, game["title"][:40], sizes["icon"], sizes["banner"])


def build_banner(game):
    if game.get("banner_from"):
        return build_banner_from(game)
    shot =root_path(game.get("title_screen", os.path.join("art", "titles", game["key"] + ".png")))
    if not os.path.exists(shot):
        raise SystemExit("no title screen picture: %s" % shot)
    return vcbanner.build(game, Image.open(shot), save_png=os.path.join(ROOT, "out", "vc_" + game["key"]))


def build_args(game):
    if game["kind"] == "nintendont":
        cfg = bytearray(open(root_path(game.get("nincfg", "nincfg.bin")), "rb").read())
        assert len(cfg) == 548 and cfg[:4] == bytes.fromhex("01070CF6"), "nincfg.bin is not a v10 NIN_CFG"
        assert struct.unpack(">I", cfg[4:8])[0] == 10
        flags = struct.unpack(">I", cfg[8:12])[0]
        flags |= 0x80 | 0x400            # NIN_CFG_AUTO_BOOT | NIN_CFG_USB
        if game.get("memcard_blocks_code") is not None:
            # A real memory card is not always seen when Nintendont starts from a channel: emulate it.
            # MEMCARDEMU 0x8 + MC_MULTI 0x2000 = one shared card usb:/saves/ninmem.raw;
            # MemCardBlocks at 0x21C: 2 = 251 blocks, 3 = 507 (CommonConfig.h). 251 is the safe size:
            # 507 froze some games on a real Wii.
            flags |= 0x8 | 0x2000
            if game.get("own_card"):
                # its own card file usb:/saves/<GameID 4>.raw (MC_MULTI off), for a mod with the same
                # game ID as the original, so the two never share a save
                flags &= ~0x2000
            cfg[0x21C] = game["memcard_blocks_code"]
        if game.get("nin_log"):
            flags |= 0x1000                # NIN_CFG_LOG: Nintendont writes ndebug.log to the drive
        struct.pack_into(">I", cfg, 8, flags)
        path = game["gamepath"].encode("ascii")
        assert len(path) < 255
        cfg[0x14:0x14 + 255] = path + b"\0" * (255 - len(path))
        cfg[0x218:0x21C] = game["id6"][:4].encode("ascii")   # GameID: first 4 letters of the disc ID
        return b"usb:/apps/nintendont/boot.dol\0" + bytes(cfg)
    return b"".join(a.encode("ascii") + b"\0" for a in game["args"])


def patch_forwarder(game, args):
    dol = bytearray(open(FWD, "rb").read())
    at = dol.find(b"WS42FWD1")
    assert at > 0 and dol.find(b"WS42FWD1", at + 1) < 0
    title = game["title"].encode("ascii", "replace")[:63]
    dolp = game["dol"].encode("ascii")
    assert len(dolp) < 128 and len(args) <= 2046
    dol[at + 8:at + 72] = title + b"\0" * (64 - len(title))
    dol[at + 72:at + 200] = dolp + b"\0" * (128 - len(dolp))
    dol[at + 200:at + 204] = struct.pack(">I", len(args))
    dol[at + 204:at + 204 + 2048] = args + b"\0" * (2048 - len(args))
    # flags: bit 0 = reload IOS 58 first (emulators get a fresh USB stack, as from the Homebrew
    # Channel; never Nintendont, which needs AHBPROT)
    dol[at + 2252:at + 2256] = struct.pack(">I", 1 if game.get("reload_ios") else 0)
    return bytes(dol)


def build_tmd(game, contents):
    t = bytearray(open(os.path.join(BASE, "base.tmd"), "rb").read()[:0x1E4])
    t[0x18C:0x194] = bytes.fromhex(game.get("tidtype", "00010001")) + game["id"].encode("ascii")
    t[0x184:0x18C] = bytes.fromhex("000000010000003a")   # IOS58
    struct.pack_into(">I", t, 0x1D8, 3)          # access rights: AHBPROT + DVD
    struct.pack_into(">HH", t, 0x1DE, len(contents), 1)
    for i, blob in enumerate(contents):
        t += struct.pack(">IHHQ", i, i, 1, len(blob)) + hashlib.sha1(blob).digest()
    return bytes(t)


def main(key):
    path = os.path.join(ROOT, "games.json")
    if not os.path.exists(path):
        raise SystemExit("no games.json: copy games.example.json to games.json and edit it")
    games = json.load(open(path, encoding="utf-8"))
    game = dict(games[key], key=key)
    assert len(game["id"]) == 4, "id must be 4 letters/digits, unique on your Wii"
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    banner = build_banner(game)
    args = build_args(game)
    fwd = patch_forwarder(game, args)

    work = os.path.join(ROOT, "out", "wad_" + key)
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    tid = game.get("tidtype", "00010001") + game["id"].encode("ascii").hex()
    open(os.path.join(work, "00000000.app"), "wb").write(banner)
    open(os.path.join(work, "00000001.app"), "wb").write(fwd)
    open(os.path.join(work, tid + ".tmd"), "wb").write(build_tmd(game, [banner, fwd]))
    for ext in ("tik", "cert", "footer"):
        shutil.copy(os.path.join(BASE, "base." + ext), os.path.join(work, tid + "." + ext))
    out = os.path.join(ROOT, "out", "%s %s.wad" % (game["id"], game["title"].replace(":", "")))
    r = subprocess.run([SHARPII, "WAD", "-p", work, out, "-id", game["id"], "-ios", "58", "-f"],
                       capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr)
    print(out, os.path.getsize(out) if os.path.exists(out) else "NOT MADE")


if __name__ == "__main__":
    main(sys.argv[1])
