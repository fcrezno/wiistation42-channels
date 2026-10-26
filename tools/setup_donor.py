"""Puts the parts of YOUR OWN SNES Virtual Console banner into donor/, for vcbanner.py.

  python -I setup_donor.py <content folder | banner .app>

The input is the DECRYPTED banner of an SNES VC channel you own (tested with Super Mario RPG,
00010001-JCBE). Two ways to get it:
  - a folder title/00010001/<id>/content from a Dolphin NAND (Dolphin keeps contents decrypted),
    or from tools/nandextract.py run on your BootMii backup: the banner is the content with
    index 0 in title.tmd;
  - the file 00000000.app from your own WAD unpacked with Sharpii (WAD -u).
Nothing from Nintendo is in this repo: the donor stays on your PC (donor/ is in .gitignore).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vcbanner  # noqa: E402
import wiibanner as wb  # noqa: E402


def banner_app(path):
    if os.path.isfile(path):
        return path
    tmd = open(os.path.join(path, "title.tmd"), "rb").read()
    n = struct.unpack(">H", tmd[0x1DE:0x1E0])[0]
    for i in range(n):
        cid, idx = struct.unpack(">IH", tmd[0x1E4 + i * 36:0x1E4 + i * 36 + 6])
        if idx == 0:
            return os.path.join(path, "%08x.app" % cid)
    raise SystemExit("no content with index 0 in title.tmd")


def main(src):
    app = open(banner_app(src), "rb").read()
    arc = wb.imet_unpack(app)
    out = vcbanner.DONOR
    for part, order in (("banner", vcbanner.ORDER_BANNER), ("icon", vcbanner.ORDER_ICON)):
        files = wb.u8_unpack(wb.imd5_unwrap(arc["meta/%s.bin" % part]))
        missing = set(order) - set(files)
        if missing:
            raise SystemExit("this is not an SNES VC banner like the tested one; missing: %s" % sorted(missing))
        for name in order:
            p = os.path.join(out, part, name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(files[name])
    open(os.path.join(out, "sound.bin"), "wb").write(arc["meta/sound.bin"])
    # check the text panes vcbanner edits are there
    vcbanner.brlyt_set_texts(files_brlyt(out), {"T_PF": "test"})
    print("donor ready in", out)


def files_brlyt(out):
    return open(os.path.join(out, "banner", "arc", "blyt", "banner.brlyt"), "rb").read()


if __name__ == "__main__":
    main(sys.argv[1])
