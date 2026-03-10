#!/usr/bin/env python3
"""
Star Wars Episode I: Racer - String Dumper
==========================================
Extracts and categorizes all readable strings from the ROM.
Useful for identifying game text, debug info, file paths, and more.

Usage: python tools/string_dumper.py [baserom.z64] [--min-length N] [--category CAT]

Categories: all, debug, game, files, menu, dialogue, credits
"""

import struct
import sys
import os
import argparse


def extract_strings(rom_data, min_length=6):
    """Extract all null-terminated ASCII strings from ROM."""
    strings = []
    i = 0x1000  # Skip header/boot code
    rom_size = len(rom_data)

    while i < rom_size - 4:
        if i > 0x1000 and rom_data[i-1] != 0:
            i += 1
            continue
        try:
            end = rom_data.index(0, i)
            if end - i >= min_length:
                s = rom_data[i:end].decode('ascii')
                if s.isprintable() and sum(c.isalpha() for c in s) >= 3:
                    strings.append((i, s))
            i = end + 1
        except (ValueError, UnicodeDecodeError):
            i += 1

    return strings


def categorize_string(text):
    """Categorize a string based on its content."""
    lower = text.lower()

    if any(kw in lower for kw in ['.c', '.h', '.s', 'assert', 'error', 'warning',
                                    'panic', 'fault', 'debug', 'trace']):
        return 'debug'

    if any(kw in lower for kw in ['data/', 'gfx/', 'audio/', 'texture', '.bin',
                                    '.dat', '.raw', '.pal']):
        return 'files'

    if any(kw in lower for kw in ['~f', '~c', '~s', '~o', '~r', '~n']):
        return 'menu'

    if any(kw in lower for kw in ['podracer', 'anakin', 'sebulba', 'watto',
                                    'tatooine', 'qui-gon', 'jedi', 'force']):
        return 'dialogue'

    if any(kw in lower for kw in ['artist', 'programmer', 'designer', 'producer',
                                    'director', 'lucasarts', 'copyright']):
        return 'credits'

    if any(kw in lower for kw in ['race', 'track', 'vehicle', 'engine', 'boost',
                                    'turbo', 'player', 'planet', 'level', 'racer',
                                    'upgrade', 'repair', 'lap', 'finish', 'start']):
        return 'game'

    return 'other'


def main():
    parser = argparse.ArgumentParser(description='SWE1R String Dumper')
    parser.add_argument('rom', nargs='?', default='baserom.z64', help='ROM file path')
    parser.add_argument('--min-length', type=int, default=6, help='Minimum string length')
    parser.add_argument('--category', '-c', default='all',
                       choices=['all', 'debug', 'game', 'files', 'menu', 'dialogue', 'credits', 'other'],
                       help='Filter by category')
    args = parser.parse_args()

    if not os.path.exists(args.rom):
        print(f"ROM not found: {args.rom}")
        sys.exit(1)

    with open(args.rom, 'rb') as f:
        rom_data = f.read()

    print(f"\n  Extracting strings (min length: {args.min_length})...")
    strings = extract_strings(rom_data, args.min_length)

    # Categorize
    categorized = {}
    for offset, text in strings:
        cat = categorize_string(text)
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append((offset, text))

    # Print summary
    print(f"\n  Total strings: {len(strings)}")
    print(f"  Categories:")
    for cat, items in sorted(categorized.items()):
        print(f"    {cat:12s}: {len(items):4d}")
    print()

    # Print filtered results
    if args.category == 'all':
        for cat in sorted(categorized.keys()):
            print(f"\n  === {cat.upper()} ({len(categorized[cat])}) ===")
            for offset, text in categorized[cat]:
                print(f"    0x{offset:06X}: {text[:80]}")
    else:
        items = categorized.get(args.category, [])
        print(f"\n  === {args.category.upper()} ({len(items)}) ===")
        for offset, text in items:
            print(f"    0x{offset:06X}: {text[:80]}")

    print()


if __name__ == '__main__':
    main()
