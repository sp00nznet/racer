"""Prints the first USA Star Wars Episode I: Racer ROM (big-endian .z64) in the given folders or
their direct subfolders; prints nothing if there's none. Used by setup.sh and setup-builds."""
import os, sys

HEADER = b"STAR WARS EP1 RACER"  # ROM header name (0x20)
CRC = "72F70398"                 # CRC1 (0x10), USA release

for top in sys.argv[1:]:
    if os.path.isfile(top):
        top = os.path.dirname(top) or "."
    if not os.path.isdir(top):
        continue
    dirs = [top] + sorted(os.path.join(top, d) for d in os.listdir(top) if os.path.isdir(os.path.join(top, d)))
    for d in dirs:
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if not os.path.isfile(p) or os.path.splitext(name)[1].lower() not in (".z64", ".n64", ".v64"):
                continue
            with open(p, "rb") as f:
                h = f.read(0x40)
            if len(h) == 0x40 and h[0x20:0x33] == HEADER and h[0x10:0x14].hex().upper() == CRC:
                print(p)
                sys.exit()
