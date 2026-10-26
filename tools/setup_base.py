"""Takes the ticket, certificate chain and TMD header from ANY channel WAD you already have
(for example a forwarder WAD for the Homebrew Channel), and puts them in base/ for makechannel.py.

  python -I setup_base.py <any channel .wad>

makechannel.py keeps only the TMD header (it writes the title ID, IOS, contents itself), and
Sharpii re-uses the ticket's title key and fakesigns the result, so any working channel WAD
does. These files are not in this repo (base/ is in .gitignore).
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARPII = os.environ.get("WS42_SHARPII", os.path.join(HERE, "Sharpii.exe"))


def main(wad):
    if not os.path.exists(SHARPII):
        raise SystemExit("Sharpii not found: put Sharpii.exe in tools/ or set WS42_SHARPII")
    base = os.path.join(ROOT, "base")
    os.makedirs(base, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([SHARPII, "WAD", "-u", wad, tmp], capture_output=True, text=True)
        for ext in ("tik", "cert", "tmd", "footer"):
            found = glob.glob(os.path.join(tmp, "*." + ext))
            if not found:
                if ext == "footer":
                    open(os.path.join(base, "base.footer"), "wb").close()
                    continue
                raise SystemExit("Sharpii did not unpack a .%s file:\n%s %s" % (ext, r.stdout, r.stderr))
            shutil.copy(found[0], os.path.join(base, "base." + ext))
    print("base ready in", base)


if __name__ == "__main__":
    main(sys.argv[1])
