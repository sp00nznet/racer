#!/usr/bin/env python3
"""
Star Wars Episode I: Racer - Libultra Function Identifier
==========================================================
Identifies Nintendo libultra OS functions in the ROM binary using
instruction pattern matching and cross-reference analysis.

Usage: python tools/libultra_identify.py [baserom.z64]
"""

import struct
import sys
import os


class LibultraIdentifier:
    def __init__(self, rom_path):
        with open(rom_path, 'rb') as f:
            self.data = f.read()
        self.identified = {}
        self.call_graph = {}  # vram -> [called_vrams]
        self.callers = {}     # vram -> [caller_vrams]
        self.call_counts = {} # vram -> call_count
        self.func_info = {}   # vram -> {size, rom, frame_size, is_leaf, ...}

    def rw(self, off):
        return struct.unpack('>I', self.data[off:off+4])[0]

    def r2v(self, off):
        return 0x80000400 + (off - 0x1000)

    def v2r(self, vram):
        return 0x1000 + (vram - 0x80000400)

    def read_instrs(self, vram, count=50):
        """Read instructions from a VRAM address."""
        off = self.v2r(vram)
        result = []
        for i in range(count):
            if off + i * 4 + 4 <= len(self.data):
                result.append(self.rw(off + i * 4))
        return result

    def find_all_functions(self):
        """Find all function prologues."""
        for i in range(0x1000, 0x99000, 4):
            w = self.rw(i)
            if (w & 0xFFFF0000) == 0x27BD0000:
                imm = w & 0xFFFF
                if imm >= 0xFF00:
                    vram = self.r2v(i)
                    frame_size = 0x10000 - imm
                    self.func_info[vram] = {
                        'rom': i,
                        'frame_size': frame_size,
                        'size': 0,
                        'is_leaf': True,
                        'calls': [],
                    }

        # Also find leaf functions (no stack frame) that are JAL targets
        # We'll add these as we discover them from the call graph

        # Calculate sizes and build call graph
        sorted_funcs = sorted(self.func_info.keys())
        for idx, vram in enumerate(sorted_funcs):
            info = self.func_info[vram]
            if idx + 1 < len(sorted_funcs):
                info['size'] = sorted_funcs[idx + 1] - vram
            else:
                info['size'] = self.r2v(0x99000) - vram

            # Scan for JAL instructions
            off = info['rom']
            for j in range(off, off + info['size'], 4):
                if j + 4 > len(self.data):
                    break
                w = self.rw(j)
                op = (w >> 26) & 0x3F
                if op == 3:  # JAL
                    target = ((w & 0x3FFFFFF) << 2) | 0x80000000
                    info['is_leaf'] = False
                    info['calls'].append(target)

                    # Track callers
                    if target not in self.callers:
                        self.callers[target] = []
                    self.callers[target].append(vram)

                    self.call_counts[target] = self.call_counts.get(target, 0) + 1

    def has_cop0_access(self, vram, max_instrs=30):
        """Check if function accesses COP0 registers."""
        instrs = self.read_instrs(vram, max_instrs)
        for w in instrs:
            if (w >> 26) == 0x10:  # COP0
                return True
        return False

    def has_hw_access(self, vram, hw_base, max_instrs=50):
        """Check if function accesses hardware registers at hw_base."""
        instrs = self.read_instrs(vram, max_instrs)
        hw_hi = (hw_base >> 16) & 0xFFFF
        for w in instrs:
            if (w >> 26) == 0x0F:  # LUI
                if (w & 0xFFFF) == hw_hi:
                    return True
        return False

    def get_func_size_exact(self, vram):
        """Get exact function size by finding JR RA."""
        off = self.v2r(vram)
        for i in range(0, 0x2000, 4):
            if off + i + 4 > len(self.data):
                break
            if self.rw(off + i) == 0x03E00008:  # JR RA
                return i + 8  # include delay slot
        return None

    def identify_by_cop0_pattern(self):
        """Identify OS functions that use COP0 instructions."""
        for vram, info in self.func_info.items():
            if vram < 0x8008C000:
                continue  # libultra is in upper range

            instrs = self.read_instrs(vram, 20)
            if not instrs:
                continue

            # Check for MFC0/MTC0 patterns
            has_mfc0 = False
            has_mtc0 = False
            mfc0_rd = -1
            mtc0_rd = -1
            func_size = self.get_func_size_exact(vram) or info['size']

            for w in instrs[:func_size // 4]:
                if (w >> 26) == 0x10:  # COP0
                    rs = (w >> 21) & 0x1F
                    rd = (w >> 11) & 0x1F
                    if rs == 0:  # MFC0
                        has_mfc0 = True
                        mfc0_rd = rd
                    elif rs == 4:  # MTC0
                        has_mtc0 = True
                        mtc0_rd = rd

            if not (has_mfc0 or has_mtc0):
                continue

            # Status register (12) access patterns
            if mfc0_rd == 12 and mtc0_rd == 12:
                if func_size <= 40:
                    self.identified[vram] = '__osDisableInt'
                else:
                    self.identified[vram] = '__osSetSR'
            elif mtc0_rd == 12 and not has_mfc0:
                if func_size <= 24:
                    self.identified[vram] = '__osRestoreInt'
            elif mfc0_rd == 9:  # Count register
                if func_size <= 12:
                    self.identified[vram] = 'osGetCount'
            elif mfc0_rd == 12 and not has_mtc0:
                if func_size <= 12:
                    self.identified[vram] = '__osGetSR'
            elif mfc0_rd == 13:  # Cause register
                self.identified[vram] = '__osGetCause'
            elif has_mfc0 or has_mtc0:
                self.identified[vram] = f'__os_cop0_func (MFC0_rd={mfc0_rd}, MTC0_rd={mtc0_rd}, size={func_size})'

    def identify_by_hw_registers(self):
        """Identify functions by hardware register access patterns."""
        hw_regions = {
            0xA4400000: 'VI',   # Video Interface
            0xA4500000: 'AI',   # Audio Interface
            0xA4600000: 'PI',   # Peripheral Interface
            0xA4800000: 'SI',   # Serial Interface
            0xA4100000: 'DP',   # RDP Command
            0xA4040000: 'SP',   # RSP
            0xA4300000: 'MI',   # MIPS Interface
        }

        for vram, info in self.func_info.items():
            if vram < 0x8008C000:
                continue

            if vram in self.identified:
                continue

            for hw_base, hw_name in hw_regions.items():
                if self.has_hw_access(vram, hw_base):
                    size = self.get_func_size_exact(vram) or info['size']

                    if hw_name == 'VI':
                        if size <= 60:
                            self.identified[vram] = f'osVi_small (size={size})'
                        elif size <= 200:
                            self.identified[vram] = f'osVi_medium (size={size})'
                        else:
                            self.identified[vram] = f'osViManager_candidate (size={size})'

                    elif hw_name == 'PI':
                        if size <= 40:
                            self.identified[vram] = f'osPiRaw_io (size={size})'
                        elif size <= 100:
                            self.identified[vram] = f'osPi_func (size={size})'
                        elif size <= 300:
                            self.identified[vram] = f'osPiStartDma_candidate (size={size})'
                        else:
                            self.identified[vram] = f'osPiManager_candidate (size={size})'

                    elif hw_name == 'SI':
                        self.identified[vram] = f'osSi_func (size={size})'

                    elif hw_name == 'SP':
                        if size <= 60:
                            self.identified[vram] = f'osSp_small (size={size})'
                        else:
                            self.identified[vram] = f'osSpTask_candidate (size={size})'

                    elif hw_name == 'AI':
                        self.identified[vram] = f'osAi_func (size={size})'

                    elif hw_name == 'DP':
                        self.identified[vram] = f'osDp_func (size={size})'

                    elif hw_name == 'MI':
                        self.identified[vram] = f'osMi_func (size={size})'

                    break  # Only classify by first match

    def identify_game_functions(self):
        """Identify common game functions by instruction patterns."""
        for vram, info in self.func_info.items():
            if vram >= 0x8008C000:
                continue  # Skip libultra range
            if vram in self.identified:
                continue

            instrs = self.read_instrs(vram, min(info['size'] // 4, 30))
            if not instrs:
                continue

            # Vector copy: LWC1/SWC1 pairs on consecutive offsets
            if len(instrs) >= 6:
                lwc1_count = sum(1 for w in instrs[:8] if (w >> 26) == 0x31)
                swc1_count = sum(1 for w in instrs[:8] if (w >> 26) == 0x39)
                if lwc1_count >= 3 and swc1_count >= 3 and info['size'] <= 40:
                    self.identified[vram] = 'vec3f_copy'
                    continue

            # Vector set: MTC1 + SWC1 patterns
            mtc1_count = sum(1 for w in instrs[:10] if (w & 0xFFE00000) == 0x44800000)
            swc1_early = sum(1 for w in instrs[:10] if (w >> 26) == 0x39)
            if mtc1_count >= 2 and swc1_early >= 3 and info['size'] <= 48:
                self.identified[vram] = 'vec3f_set'
                continue

            # Memory allocation pattern: accesses a global pointer, adds to it
            # Common pattern: LUI + LW (load global), ADDIU (bump pointer), SW (store back)
            if self.call_counts.get(vram, 0) > 100 and not info['is_leaf']:
                # Heavily called non-leaf = likely utility
                pass

            # Math functions: all-float operations, small size
            float_ops = sum(1 for w in instrs[:20] if (w >> 26) in (0x31, 0x39, 0x35, 0x3D)
                          or ((w >> 26) == 0x11))  # COP1 (float math)
            total_instrs = min(len(instrs), 20)
            if total_instrs > 4 and float_ops / total_instrs > 0.5:
                if info['size'] <= 80:
                    self.identified[vram] = 'math_float_func'
                elif info['size'] <= 200:
                    self.identified[vram] = 'math_vector_func'

    def identify_by_string_refs(self):
        """Identify functions that reference known strings."""
        # Find strings and their addresses
        string_refs = {
            'AudioInfo': 'audio_info_func',
            'Debug Level': 'debug_menu_func',
            'Boost Thrust': 'vehicle_stats_func',
            'Edit Vehicle Stats': 'edit_vehicle_func',
            'Restart Race': 'restart_race_func',
            'Start Race': 'start_race_func',
            'Main Menu': 'main_menu_func',
            'Star Wars': 'title_screen_func',
            'Select Vehicle': 'vehicle_select_func',
            'Select Player': 'player_select_func',
            'Vehicle Statistics': 'vehicle_stats_display_func',
            'Planet not loaded': 'planet_load_error_func',
            'Low Memory': 'low_memory_handler',
            'ENGINE': 'engine_fire_func',
        }

        # Find string addresses
        string_addrs = {}
        for i in range(0x1000, len(self.data) - 20):
            if i > 0x1000 and self.data[i-1] != 0:
                continue
            try:
                end = self.data.index(0, i)
                if end - i >= 4:
                    s = self.data[i:end].decode('ascii')
                    for key, name in string_refs.items():
                        if key in s and key not in string_addrs:
                            # VRAM of the string
                            string_addrs[key] = {
                                'rom': i,
                                'name': name,
                            }
                i = end + 1
            except:
                i += 1

        # Now find functions that load these string addresses via LUI+ADDIU/ORI
        for key, info in string_addrs.items():
            rom_addr = info['rom']
            # The string's VRAM address (data is typically loaded relative to ROM)
            # In N64, data addresses are accessed via LUI hi + ADDIU/ORI lo
            # We'd need to know the data segment VRAM mapping
            # For now, just note the string locations
            pass

    def identify_by_call_count(self):
        """Use call frequency heuristics to name common functions."""
        # Sort by call count
        sorted_by_calls = sorted(self.call_counts.items(), key=lambda x: x[1], reverse=True)

        for vram, count in sorted_by_calls[:50]:
            if vram in self.identified:
                continue
            if vram not in self.func_info:
                # This is a leaf function we haven't catalogued
                size = self.get_func_size_exact(vram)
                if size and size <= 16:
                    # Tiny leaf - likely a simple getter
                    self.identified[vram] = f'getter_or_utility (calls={count}, size={size})'

    def run(self):
        """Run all identification passes."""
        print("\n  Phase 1: Discovering functions...")
        self.find_all_functions()
        print(f"    Found {len(self.func_info)} functions with prologues")
        print(f"    Found {len(self.call_counts)} unique JAL targets")

        print("  Phase 2: Identifying COP0 (OS) functions...")
        self.identify_by_cop0_pattern()

        print("  Phase 3: Identifying hardware register functions...")
        self.identify_by_hw_registers()

        print("  Phase 4: Identifying game functions...")
        self.identify_game_functions()

        print("  Phase 5: Analyzing call frequency...")
        self.identify_by_call_count()

        print("  Phase 6: Cross-referencing strings...")
        self.identify_by_string_refs()

        # Summary
        print(f"\n  Total identified: {len(self.identified)} functions")
        print()

        # Print by category
        categories = {}
        for vram, name in sorted(self.identified.items()):
            if name.startswith('os') or name.startswith('__os'):
                cat = 'libultra'
            elif name.startswith('vec') or name.startswith('math'):
                cat = 'math'
            elif 'candidate' in name:
                cat = 'candidates'
            else:
                cat = 'game'
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((vram, name))

        for cat in ['libultra', 'math', 'game', 'candidates']:
            if cat not in categories:
                continue
            items = categories[cat]
            print(f"  === {cat.upper()} ({len(items)}) ===")
            for vram, name in items:
                count = self.call_counts.get(vram, 0)
                print(f"    0x{vram:08X}: {name:40s} (called {count}x)")
            print()

        return self.identified

    def update_symbols_toml(self, symbols_path='symbols.toml'):
        """Update symbols.toml with identified function names."""
        if not os.path.exists(symbols_path):
            print(f"  {symbols_path} not found!")
            return

        with open(symbols_path, 'r') as f:
            content = f.read()

        updated = 0
        for vram, name in self.identified.items():
            old_name = f'func_{vram:08X}'
            # Clean up candidate names for the symbol file
            clean_name = name.split(' ')[0].replace('(', '').replace(')', '')
            if old_name in content:
                content = content.replace(f'name = "{old_name}"', f'name = "{clean_name}"')
                updated += 1

        with open(symbols_path, 'w') as f:
            f.write(content)

        print(f"  Updated {updated} function names in {symbols_path}")


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else 'baserom.z64'

    if not os.path.exists(rom_path):
        print(f"ROM not found: {rom_path}")
        sys.exit(1)

    print()
    print("  ================================================")
    print("  =  LIBULTRA FUNCTION IDENTIFIER                =")
    print("  =  \"Use the Force, Luke\" (but for RE)           =")
    print("  ================================================")

    identifier = LibultraIdentifier(rom_path)
    identified = identifier.run()

    if '--update' in sys.argv:
        print("  Updating symbols.toml...")
        identifier.update_symbols_toml()
        print("  Done!")
    else:
        print("  Run with --update to apply names to symbols.toml")

    print()


if __name__ == '__main__':
    main()
