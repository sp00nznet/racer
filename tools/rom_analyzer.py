#!/usr/bin/env python3
"""
Star Wars Episode I: Racer - ROM Analyzer
==========================================
Analyzes the N64 ROM to discover functions, strings, and data sections.
Outputs symbol information for use with N64Recomp.

Usage: python tools/rom_analyzer.py [baserom.z64]
"""

import struct
import sys
import os
from collections import defaultdict

# ROM constants for SWE1R US
ROM_ENTRY_POINT = 0x80000400
ROM_CODE_START = 0x1000
ROM_TITLE = "STAR WARS EP1 RACER"
ROM_GAME_CODE = "NEPE"
EXPECTED_CRC1 = 0x72F70398
EXPECTED_CRC2 = 0x6556A98B
EXPECTED_SIZE = 33554432  # 32 MB

# MIPS instruction constants
MIPS_OP_MASK = 0xFC000000
MIPS_ADDIU_SP = 0x27BD0000  # ADDIU SP, SP, imm
MIPS_JR_RA = 0x03E00008     # JR RA (function return)
MIPS_NOP = 0x00000000

# Common MIPS opcodes for instruction density analysis
COMMON_OPCODES = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                  35, 43, 39, 37, 36, 40, 41, 17}


class RomAnalyzer:
    def __init__(self, rom_path):
        with open(rom_path, 'rb') as f:
            self.data = f.read()
        self.rom_size = len(self.data)
        self.functions = []
        self.strings = []
        self.sections = []

    def read_word(self, offset):
        """Read a big-endian 32-bit word from ROM."""
        return struct.unpack('>I', self.data[offset:offset+4])[0]

    def rom_to_vram(self, rom_offset):
        """Convert ROM offset to VRAM address."""
        return ROM_ENTRY_POINT + (rom_offset - ROM_CODE_START)

    def vram_to_rom(self, vram):
        """Convert VRAM address to ROM offset."""
        return ROM_CODE_START + (vram - ROM_ENTRY_POINT)

    def verify_rom(self):
        """Verify ROM header and integrity."""
        print("=" * 60)
        print("  ROM VERIFICATION")
        print("=" * 60)

        title = self.data[0x20:0x34].decode('ascii', errors='replace').strip()
        game_code = self.data[0x3B:0x3F].decode('ascii', errors='replace')
        entry = self.read_word(8)
        crc1 = self.read_word(16)
        crc2 = self.read_word(20)

        print(f"  Title:      {title}")
        print(f"  Game Code:  {game_code}")
        print(f"  Entry:      0x{entry:08X}")
        print(f"  CRC1:       0x{crc1:08X} {'OK' if crc1 == EXPECTED_CRC1 else 'MISMATCH!'}")
        print(f"  CRC2:       0x{crc2:08X} {'OK' if crc2 == EXPECTED_CRC2 else 'MISMATCH!'}")
        print(f"  Size:       {self.rom_size:,} bytes {'OK' if self.rom_size == EXPECTED_SIZE else 'UNEXPECTED!'}")
        print()

        return (crc1 == EXPECTED_CRC1 and crc2 == EXPECTED_CRC2 and
                self.rom_size == EXPECTED_SIZE)

    def find_functions(self, start=ROM_CODE_START, end=None):
        """Find function prologues by scanning for ADDIU SP, SP, -N patterns."""
        if end is None:
            end = self.find_code_end()

        self.functions = []
        for i in range(start, end, 4):
            word = self.read_word(i)
            if (word & 0xFFFF0000) == 0x27BD0000:
                imm = word & 0xFFFF
                if imm >= 0xFF00:  # Negative immediate = stack frame allocation
                    frame_size = 0x10000 - imm
                    vram = self.rom_to_vram(i)
                    self.functions.append({
                        'rom': i,
                        'vram': vram,
                        'frame_size': frame_size,
                        'name': f'func_{vram:08X}',
                        'size': 0  # Calculated later
                    })

        # Calculate function sizes
        for idx in range(len(self.functions)):
            if idx + 1 < len(self.functions):
                self.functions[idx]['size'] = (
                    self.functions[idx + 1]['rom'] - self.functions[idx]['rom']
                )
            else:
                self.functions[idx]['size'] = end - self.functions[idx]['rom']

        print(f"  Found {len(self.functions)} functions in range "
              f"0x{start:06X}-0x{end:06X}")
        return self.functions

    def find_code_end(self):
        """Find where executable code ends by analyzing instruction density."""
        last_code = ROM_CODE_START
        block_size = 0x4000

        for base in range(ROM_CODE_START, min(self.rom_size, 0x200000), block_size):
            mips_count = 0
            total = block_size // 4
            for j in range(base, base + block_size, 4):
                word = self.read_word(j)
                op = (word >> 26) & 0x3F
                if op in COMMON_OPCODES:
                    mips_count += 1
            density = mips_count / total
            if density > 0.60:
                last_code = base + block_size

        print(f"  Code region ends at approximately ROM 0x{last_code:06X} "
              f"(VRAM 0x{self.rom_to_vram(last_code):08X})")
        return last_code

    def find_strings(self, min_length=6):
        """Find null-terminated ASCII strings in the ROM."""
        self.strings = []
        i = ROM_CODE_START

        while i < self.rom_size - 4:
            if i > ROM_CODE_START and self.data[i-1] != 0:
                i += 1
                continue
            try:
                end = self.data.index(0, i)
                if end - i >= min_length:
                    s = self.data[i:end].decode('ascii')
                    if s.isprintable() and sum(c.isalpha() for c in s) >= 4:
                        self.strings.append({'offset': i, 'text': s})
                i = end + 1
            except (ValueError, UnicodeDecodeError):
                i += 1

        print(f"  Found {len(self.strings)} strings")
        return self.strings

    def find_debug_strings(self):
        """Find strings that suggest debug/development info (source files, asserts, etc.)."""
        debug_keywords = ['.c', '.h', '.s', 'debug', 'error', 'assert', 'warning',
                         'panic', 'fault', 'crash', 'trace', 'printf', 'sprintf']
        results = []
        for s in self.strings:
            if any(kw in s['text'].lower() for kw in debug_keywords):
                results.append(s)
        return results

    def find_game_strings(self):
        """Find game-specific strings (menus, dialogue, etc.)."""
        game_keywords = ['race', 'track', 'vehicle', 'engine', 'boost', 'turbo',
                        'player', 'menu', 'planet', 'racer', 'podracer', 'anakin',
                        'sebulba', 'watto', 'tatooine', 'camera', 'audio', 'level']
        results = []
        for s in self.strings:
            if any(kw in s['text'].lower() for kw in game_keywords):
                results.append(s)
        return results

    def generate_symbols_toml(self, output_path='symbols.toml'):
        """Generate a symbols.toml file for N64Recomp."""
        if not self.functions:
            self.find_functions()

        code_end = self.functions[-1]['rom'] + self.functions[-1]['size'] if self.functions else 0x99000
        section_size = code_end - ROM_CODE_START

        lines = [
            '# Star Wars Episode I: Racer (US) - Symbol Definitions',
            '# Generated by rom_analyzer.py',
            f'# {len(self.functions)} functions discovered via prologue detection',
            '',
            '[[section]]',
            'name = "code"',
            f'rom = 0x{ROM_CODE_START:X}',
            f'vram = 0x{ROM_ENTRY_POINT:08X}',
            f'size = 0x{section_size:X}',
            '',
        ]

        for func in self.functions:
            lines.extend([
                '  [[section.functions]]',
                f'  name = "{func["name"]}"',
                f'  vram = 0x{func["vram"]:08X}',
                f'  size = 0x{func["size"]:X}',
                '',
            ])

        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))

        print(f"  Wrote {output_path} ({len(self.functions)} functions)")

    def print_summary(self):
        """Print a summary of the analysis."""
        print()
        print("=" * 60)
        print("  ANALYSIS SUMMARY")
        print("=" * 60)
        print(f"  ROM Size:       {self.rom_size:,} bytes ({self.rom_size / 1024 / 1024:.1f} MB)")
        print(f"  Functions:      {len(self.functions)}")
        print(f"  Strings:        {len(self.strings)}")

        if self.functions:
            total_code = sum(f['size'] for f in self.functions)
            avg_size = total_code / len(self.functions)
            biggest = max(self.functions, key=lambda f: f['size'])
            smallest = min(self.functions, key=lambda f: f['size'])

            print(f"  Total code:     {total_code:,} bytes ({total_code / 1024:.1f} KB)")
            print(f"  Avg func size:  {avg_size:.0f} bytes")
            print(f"  Biggest func:   {biggest['name']} ({biggest['size']:,} bytes)")
            print(f"  Smallest func:  {smallest['name']} ({smallest['size']} bytes)")

        debug = self.find_debug_strings()
        if debug:
            print(f"\n  Debug strings:  {len(debug)}")
            for s in debug[:10]:
                print(f"    0x{s['offset']:06X}: {s['text'][:60]}")

        game = self.find_game_strings()
        if game:
            print(f"\n  Game strings:   {len(game)}")
            for s in game[:10]:
                print(f"    0x{s['offset']:06X}: {s['text'][:60]}")

        print()


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else 'baserom.z64'

    if not os.path.exists(rom_path):
        print(f"ROM not found: {rom_path}")
        print("Place your ROM as 'baserom.z64' or pass path as argument")
        sys.exit(1)

    print()
    print("  ================================================")
    print("  =  STAR WARS EPISODE I: RACER - ROM ANALYZER   =")
    print("  =  \"Now THIS is podracing!\"                     =")
    print("  ================================================")
    print()

    analyzer = RomAnalyzer(rom_path)

    if not analyzer.verify_rom():
        print("  WARNING: ROM verification failed!")
        print("  Expected US version: STAR WARS EP1 RACER (NEPE)")
        print()

    print("  Analyzing code sections...")
    analyzer.find_functions()

    print("  Scanning for strings...")
    analyzer.find_strings()

    analyzer.print_summary()

    # Generate symbols file
    print("  Generating symbols.toml...")
    analyzer.generate_symbols_toml()

    print("  Done! May the Force be with your recompilation.")
    print()


if __name__ == '__main__':
    main()
