# WiiStation 42 channels

Make your own **Wii Menu channels** for your games, in the style of the Virtual Console:
a tile with the game's title screen, a banner with the name, year and players, and one click
from the Wii Menu into the game. **No emulator menu, no loader menu.** When you quit the game,
you go back to the Wii Menu.

- **GameCube games** start in [Nintendont](https://github.com/FIX94/Nintendont) from a USB drive.
- **SNES, Game Boy / Color / Advance, NES, Genesis** games start in the GX emulators
  (Snes9x GX, Visual Boy Advance GX, FCE Ultra GX, Genesis Plus GX), with the ROM file
  given to the emulator.

Made by **crezno** for a softmodded Wii on a CRT. Tested on a real US Wii (System Menu 4.3U) and in Dolphin.

> This repo has **no** Nintendo files, no games, no ROMs, no title screens and no keys.
> You make the channels from files that **you** own. Do not share the WADs you make: they contain
> parts of a Nintendo banner.

## How it works

Each channel is a small WAD with two parts:

1. **Banner** (`tools/vcbanner.py`): a real SNES Virtual Console banner from your own Wii is the
   "donor". The tool puts your game's title screen into it and changes the texts
   (title, year, players, ESRB, console). The Wii draws the texts in its own font, so it looks like a real VC channel.
2. **Forwarder** (`forwarder/`): a small Wii program. It mounts the SD card or the USB drive,
   loads the emulator or Nintendont, and starts it with the game's arguments.
   `tools/makechannel.py` writes the values for each game into the forwarder.

## What you need

- A softmodded Wii (Homebrew Channel) and a WAD manager, for example
  [YAWM ModMii Edition](https://github.com/modmii/YAWM-ModMii-Edition).
- Nintendont and/or the GX emulators on the SD card or USB drive, the same as for the Homebrew Channel.
- **An SNES Virtual Console channel that you own** (bought from the Wii Shop), to use as the donor.
  Tested with *Super Mario RPG* (00010001-JCBE).
- **Any channel WAD** that you already have, for the ticket and certificate files (`setup_base.py`).
- Windows with Python 3.10+ and Pillow (`pip install pillow`).
- [Sharpii](https://github.com/mogzol/sharpii) (`Sharpii.exe` in `tools/`, or set `WS42_SHARPII`).
- For GameCube games: your `nincfg.bin` from Nintendont (start Nintendont once, choose your
  settings, and copy `nincfg.bin` from the root of the drive into this folder).

## Setup (once)

1. **The donor banner.** You need the *decrypted* banner of your SNES VC channel. Choose one:
   - Make a BootMii NAND backup, then
     `python tools/nandextract.py nand-out path/to/nand.bin path/to/keys.bin`, and use
     `nand-out/title/00010001/<id>/content`; or
   - if your Dolphin has your NAND, use `Dolphin Emulator/Wii/title/00010001/<id>/content`.

   Then run:
   ```
   python tools/setup_donor.py "<that content folder>"
   ```
   The id is in hex. For example, JCBE = `4a434245`.
2. **The base files:** `python tools/setup_base.py "<any channel>.wad"`
3. **Your games:** copy `games.example.json` to `games.json` and change it (see below).
4. **Title screens:** one PNG per game in `art/titles/<key>.png` (see `art/titles/README.md`).
5. Optional: console logos in `art/logos/` (see `art/logos/README.md`).

## Make a channel

```
python tools/makechannel.py pikmin
```

The WAD goes to `out/`. Copy it to your SD card or USB drive and install it with your WAD manager.

## games.json

| field | meaning |
|---|---|
| key (the name of the entry) | used on the command line and for `art/titles/<key>.png` |
| `id` | 4 letters/digits, **different for each channel on your Wii**. Do not use the ID of a real channel. |
| `title` | the name on the banner and the Wii Menu |
| `system` | the console text and logo, e.g. `NINTENDO GAMECUBE`, `GAME BOY COLOR`. Other text = the SNES look |
| `year`, `players`, `esrb` | the texts on the banner |
| `vc_title` | optional: a longer title for the banner (a `: ` starts a second line) |
| `kind` | `nintendont` or `emu` |
| `dol` | the program the forwarder starts, e.g. `usb:/apps/nintendont/boot.dol` or `sd:/apps/snes9xgx/boot.dol` |
| `args` (emu) | the arguments: `[dol path, ROM folder, ROM file name without extension]` |
| `gamepath`, `id6` (nintendont) | the game on the USB drive (path from the root of the drive) and its 6-letter disc ID |
| `memcard_blocks_code` (nintendont) | turns on memory card emulation with one shared card `usb:/saves/ninmem.raw`. `2` = 251 blocks (recommended). `3` = 507 blocks froze some games on a real Wii. |
| `own_card` | optional: the game gets its own card file (for a mod with the same disc ID as the original game) |
| `reload_ios` | optional: reload IOS58 before the emulator starts |
| `title_screen` | optional: path to the title-screen picture |
| `nincfg` | optional: path to nincfg.bin (default `nincfg.bin`) |

## Things we found (read before you file a bug)

- **Start the emulators from the SD card** (`sd:/apps/...`). Started from the USB drive through a
  channel, some emulators opened their own menu or crashed. The ROMs can stay on the USB drive.
- **Nintendont from a channel does not always see a real memory card.** Use `memcard_blocks_code`.
  To copy your real card into `ninmem.raw`, make a raw backup with GCMM. `tools/gccard_repack.py` can
  move a 507-block card into a 251-block card. `tools/gccard_import.py` copies one save between two
  card files. It is new and not yet tested on a Wii, so keep backups.
- **The Wii Menu shows at most 48 channels.** A channel that installs with no error but does not show
  may be past that limit.
- `tools/hidetitle.py` changes a WAD's title type (for example to a hidden title). Sharpii always
  writes 00010001.
- `tools/dolphin_test.ps1` starts a WAD in Dolphin and saves pictures of Dolphin's window.

## Build the forwarder (optional)

`forwarder/forwarder.dol` is ready to use. It is the build that was tested on a real Wii. Since then,
the source changed in comments and in two error messages only. To build it yourself, you need devkitPPC and
**libogc2**. Then run `bash forwarder/build.sh` (it also builds `exitstub/`, which is linked but not used).

## Credits

- The idea of building channels from a real VC banner comes from the GameCube-to-VC banner projects
  of the Wii homebrew scene.
- Nintendont (FIX94 and others), the GX emulators (dborth and others), Sharpii (mogzol and others),
  libogc2 (extremscorner), devkitPro.

## Licence

MIT (see `LICENSE`) for the code in this repo. Nintendo, Wii, GameCube, Virtual Console and the console
names are trademarks of their owners. This project has no connection to Nintendo.
