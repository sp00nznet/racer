#!/usr/bin/env python3
"""
Star Wars Episode I: Racer - Function Differ
=============================================
Disassembles and displays individual functions from the ROM.
Inspired by DKR decomp's diff.sh tool.

Usage: python tools/func_differ.py <func_name_or_vram> [baserom.z64]
Examples:
    python tools/func_differ.py func_80000470
    python tools/func_differ.py 0x80000470
"""

import struct
import sys
import os

# MIPS register names
REG_NAMES = [
    'zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
    't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
    's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
    't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'
]

# MIPS opcode table (simplified)
OPCODES = {
    0x00: 'SPECIAL', 0x01: 'REGIMM', 0x02: 'j', 0x03: 'jal',
    0x04: 'beq', 0x05: 'bne', 0x06: 'blez', 0x07: 'bgtz',
    0x08: 'addi', 0x09: 'addiu', 0x0A: 'slti', 0x0B: 'sltiu',
    0x0C: 'andi', 0x0D: 'ori', 0x0E: 'xori', 0x0F: 'lui',
    0x10: 'COP0', 0x11: 'COP1', 0x14: 'beql', 0x15: 'bnel',
    0x20: 'lb', 0x21: 'lh', 0x23: 'lw', 0x24: 'lbu',
    0x25: 'lhu', 0x26: 'lwr', 0x27: 'lwu',
    0x28: 'sb', 0x29: 'sh', 0x2B: 'sw',
    0x31: 'lwc1', 0x35: 'ldc1', 0x39: 'swc1', 0x3D: 'sdc1',
}

SPECIAL_FUNCS = {
    0x00: 'sll', 0x02: 'srl', 0x03: 'sra', 0x04: 'sllv',
    0x06: 'srlv', 0x07: 'srav', 0x08: 'jr', 0x09: 'jalr',
    0x0C: 'syscall', 0x0D: 'break', 0x10: 'mfhi', 0x11: 'mthi',
    0x12: 'mflo', 0x13: 'mtlo', 0x18: 'mult', 0x19: 'multu',
    0x1A: 'div', 0x1B: 'divu', 0x20: 'add', 0x21: 'addu',
    0x22: 'sub', 0x23: 'subu', 0x24: 'and', 0x25: 'or',
    0x26: 'xor', 0x27: 'nor', 0x2A: 'slt', 0x2B: 'sltu',
}


def disassemble_instruction(word, pc):
    """Simple MIPS disassembler for a single instruction."""
    if word == 0:
        return "nop"

    op = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    sa = (word >> 6) & 0x1F
    func = word & 0x3F
    imm = word & 0xFFFF
    simm = imm if imm < 0x8000 else imm - 0x10000
    target = (word & 0x3FFFFFF) << 2

    if op == 0x00:  # SPECIAL
        name = SPECIAL_FUNCS.get(func, f'special_{func:02X}')
        if func in (0x00, 0x02, 0x03):  # shifts
            return f"{name} {REG_NAMES[rd]}, {REG_NAMES[rt]}, {sa}"
        elif func == 0x08:  # jr
            return f"jr {REG_NAMES[rs]}"
        elif func == 0x09:  # jalr
            return f"jalr {REG_NAMES[rs]}"
        elif func in (0x18, 0x19, 0x1A, 0x1B):  # mult/div
            return f"{name} {REG_NAMES[rs]}, {REG_NAMES[rt]}"
        elif func in (0x10, 0x12):  # mfhi/mflo
            return f"{name} {REG_NAMES[rd]}"
        else:
            return f"{name} {REG_NAMES[rd]}, {REG_NAMES[rs]}, {REG_NAMES[rt]}"
    elif op in (0x02, 0x03):  # j/jal
        name = OPCODES.get(op, f'op_{op:02X}')
        addr = (pc & 0xF0000000) | target
        return f"{name} 0x{addr:08X}"
    elif op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15):  # branches
        name = OPCODES.get(op, f'op_{op:02X}')
        branch_target = pc + 4 + (simm << 2)
        if op in (0x06, 0x07):
            return f"{name} {REG_NAMES[rs]}, 0x{branch_target:08X}"
        return f"{name} {REG_NAMES[rs]}, {REG_NAMES[rt]}, 0x{branch_target:08X}"
    elif op == 0x0F:  # lui
        return f"lui {REG_NAMES[rt]}, 0x{imm:04X}"
    elif op in (0x08, 0x09, 0x0A, 0x0B):  # arithmetic immediate
        name = OPCODES.get(op, f'op_{op:02X}')
        return f"{name} {REG_NAMES[rt]}, {REG_NAMES[rs]}, {simm}"
    elif op in (0x0C, 0x0D, 0x0E):  # logic immediate
        name = OPCODES.get(op, f'op_{op:02X}')
        return f"{name} {REG_NAMES[rt]}, {REG_NAMES[rs]}, 0x{imm:04X}"
    elif op in (0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x28, 0x29, 0x2B):  # load/store
        name = OPCODES.get(op, f'op_{op:02X}')
        return f"{name} {REG_NAMES[rt]}, {simm}({REG_NAMES[rs]})"
    elif op in (0x31, 0x35, 0x39, 0x3D):  # FP load/store
        name = OPCODES.get(op, f'op_{op:02X}')
        return f"{name} f{rt}, {simm}({REG_NAMES[rs]})"
    else:
        return f".word 0x{word:08X}  # op={op:02X}"


def load_symbols(symbols_path='symbols.toml'):
    """Load function symbols from symbols.toml."""
    funcs = {}
    current_name = None
    current_vram = None
    current_size = None

    if not os.path.exists(symbols_path):
        return funcs

    with open(symbols_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('name = "'):
                current_name = line.split('"')[1]
            elif line.startswith('vram = '):
                current_vram = int(line.split('=')[1].strip(), 16)
            elif line.startswith('size = '):
                current_size = int(line.split('=')[1].strip(), 16)
                if current_name and current_vram and current_size:
                    funcs[current_name] = {
                        'vram': current_vram,
                        'size': current_size,
                        'rom': 0x1000 + (current_vram - 0x80000400)
                    }
                    funcs[f'0x{current_vram:08X}'] = funcs[current_name]
                    funcs[f'0x{current_vram:x}'] = funcs[current_name]

    return funcs


def disassemble_function(rom_data, func_info, symbols):
    """Disassemble a complete function."""
    rom_start = func_info['rom']
    vram_start = func_info['vram']
    size = func_info['size']

    print(f"\n{'='*60}")
    print(f"  Function at VRAM 0x{vram_start:08X} (ROM 0x{rom_start:06X})")
    print(f"  Size: {size} bytes ({size // 4} instructions)")
    print(f"{'='*60}\n")

    for offset in range(0, size, 4):
        rom_addr = rom_start + offset
        vram_addr = vram_start + offset
        word = struct.unpack('>I', rom_data[rom_addr:rom_addr+4])[0]
        disasm = disassemble_instruction(word, vram_addr)

        # Add arrow for branch targets within this function
        marker = "  "
        if offset == 0:
            marker = "> "

        print(f"  {marker}{vram_addr:08X}: {word:08X}  {disasm}")

    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/func_differ.py <func_name_or_vram> [baserom.z64]")
        print("Examples:")
        print("  python tools/func_differ.py func_80000470")
        print("  python tools/func_differ.py 0x80000470")
        sys.exit(1)

    func_query = sys.argv[1]
    rom_path = sys.argv[2] if len(sys.argv) > 2 else 'baserom.z64'

    if not os.path.exists(rom_path):
        print(f"ROM not found: {rom_path}")
        sys.exit(1)

    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    symbols = load_symbols()

    if not symbols:
        print("No symbols.toml found. Run rom_analyzer.py first.")
        sys.exit(1)

    # Look up the function
    func_info = symbols.get(func_query)
    if not func_info:
        # Try with/without 0x prefix
        if func_query.startswith('0x'):
            func_info = symbols.get(func_query[2:])
        else:
            func_info = symbols.get(f'0x{func_query}')

    if not func_info:
        print(f"Function not found: {func_query}")
        print(f"Available functions: {len(symbols) // 3}")
        # Show closest matches
        query_lower = func_query.lower()
        matches = [k for k in symbols if query_lower in k.lower() and not k.startswith('0x')]
        if matches:
            print(f"Did you mean: {', '.join(matches[:10])}")
        sys.exit(1)

    disassemble_function(rom_data, func_info, symbols)


if __name__ == '__main__':
    main()
