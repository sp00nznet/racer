#!/usr/bin/env python3
"""Identify libultra functions in the SWE1R ROM by instruction patterns."""
import struct
import sys

ROM_PATH = "baserom.z64"
ROM_OFFSET = 0x1000  # ROM data starts at file offset 0x1000 (after header)
BASE_VRAM = 0x80000000

def vram_to_rom(vram):
    """Convert VRAM address to ROM file offset."""
    return (vram - BASE_VRAM) + ROM_OFFSET

def read_instructions(rom_data, vram, count=20):
    """Read MIPS instructions from ROM at given VRAM address."""
    offset = vram_to_rom(vram)
    instrs = []
    for i in range(count):
        word = struct.unpack('>I', rom_data[offset + i*4 : offset + i*4 + 4])[0]
        instrs.append(word)
    return instrs

def decode_op(instr):
    """Basic MIPS instruction decode."""
    op = (instr >> 26) & 0x3F
    rs = (instr >> 21) & 0x1F
    rt = (instr >> 16) & 0x1F
    rd = (instr >> 11) & 0x1F
    sa = (instr >> 6) & 0x1F
    funct = instr & 0x3F
    imm = instr & 0xFFFF
    target = instr & 0x3FFFFFF
    return op, rs, rt, rd, sa, funct, imm, target

def is_jal(instr):
    return (instr >> 26) == 3

def jal_target(instr):
    return ((instr & 0x3FFFFFF) << 2) | 0x80000000

def is_jr_ra(instr):
    return instr == 0x03E00008

def is_mfc0(instr, rd_check=None):
    """MFC0 rt, rd (COP0 read)"""
    op, rs, rt, rd, sa, funct, imm, target = decode_op(instr)
    if op == 0x10 and rs == 0:  # COP0, MF
        if rd_check is not None:
            return rd == rd_check
        return True
    return False

def is_mtc0(instr, rd_check=None):
    """MTC0 rt, rd (COP0 write)"""
    op, rs, rt, rd, sa, funct, imm, target = decode_op(instr)
    if op == 0x10 and rs == 4:  # COP0, MT
        if rd_check is not None:
            return rd == rd_check
        return True
    return False

def identify_function(rom_data, vram, name, size):
    """Try to identify a libultra function by its instruction pattern."""
    try:
        n_instrs = min(size // 4, 40)
        instrs = read_instructions(rom_data, vram, n_instrs)
    except:
        return None

    # __osDisableInt: mfc0 Status, andi 0x1, clear bit 0, mtc0 Status
    if n_instrs >= 4:
        if is_mfc0(instrs[0], 12):  # mfc0 ?, Status
            if (instrs[2] & 0xFC000000) == 0x30000000:  # ANDI
                return "__osDisableInt"

    # __osRestoreInt: or Status with arg, mtc0 Status
    if n_instrs >= 3:
        op0, rs0, rt0, rd0, _, funct0, _, _ = decode_op(instrs[0])
        if op0 == 0 and funct0 == 0x25:  # OR
            if is_mtc0(instrs[1], 12):  # mtc0 ?, Status
                return "__osRestoreInt"

    # osGetCount: mfc0 ?, Count (rd=9)
    if n_instrs >= 2:
        if is_mfc0(instrs[0], 9):  # mfc0 ?, Count
            return "osGetCount"

    # __osSetFpcCsr: cfc1/ctc1 pattern
    if n_instrs >= 3:
        if (instrs[0] & 0xFFE00000) == 0x44400000:  # CFC1
            if (instrs[1] & 0xFFE00000) == 0x44C00000:  # CTC1
                return "__osSetFpcCsr"

    # __osSetSR: mtc0 a0, Status; jr ra
    if n_instrs >= 2:
        if is_mtc0(instrs[0], 12) and is_jr_ra(instrs[1]):
            return "__osSetSR"

    # __osGetSR: mfc0 v0, Status; jr ra
    if n_instrs >= 2:
        if is_mfc0(instrs[0], 12) and is_jr_ra(instrs[1]):
            return "__osGetSR"

    # Functions that start with addiu sp, sp, -XX (function prologue)
    if n_instrs >= 2:
        op0 = (instrs[0] >> 26) & 0x3F
        rs0 = (instrs[0] >> 21) & 0x1F
        rt0 = (instrs[0] >> 16) & 0x1F
        if op0 == 0x09 and rs0 == 29 and rt0 == 29:  # addiu sp, sp, -XX
            frame_size = -(struct.unpack('>h', struct.pack('>H', instrs[0] & 0xFFFF))[0])

            # Check for JAL calls in the function
            jal_targets = []
            for i in range(n_instrs):
                if is_jal(instrs[i]):
                    jal_targets.append(jal_target(instrs[i]))

            # osCreateMesgQueue: small function, writes to struct fields
            # 3 args (a0=queue, a1=buf, a2=count), writes to struct at a0
            if size <= 0x40:
                # Check if it stores to multiple offsets of a0
                stores_to_a0 = 0
                for i in range(n_instrs):
                    op = (instrs[i] >> 26) & 0x3F
                    rs = (instrs[i] >> 21) & 0x1F
                    if op == 0x2B and rs == 4:  # SW to (a0 + offset)
                        stores_to_a0 += 1
                if stores_to_a0 >= 3:
                    return "osCreateMesgQueue (candidate)"

            # Look for functions that call __osDisableInt and __osRestoreInt
            calls_disable = any(t == 0x8008CA80 for t in jal_targets)
            calls_restore = any(t == 0x8008CAA0 for t in jal_targets)
            calls_enqueue = any(t == 0x8008D22C for t in jal_targets)
            calls_dequeue = any(t == 0x8008D274 for t in jal_targets)

            if calls_disable and (calls_enqueue or calls_dequeue):
                if calls_dequeue and size > 0x100:
                    return "osRecvMesg or osSendMesg (candidate)"
                elif calls_enqueue:
                    return "osStartThread (candidate)"

            # osSetEventMesg: dispatches by event type, stores queue/msg pointers
            # Look for multiple branch comparisons (beq/bne with small immediates)

            # osCreateViManager: large function with VI register accesses
            if size >= 0x200:
                has_vi_reg = False
                for i in range(n_instrs):
                    if (instrs[i] & 0xFFFF0000) == 0x3C01A440:  # lui at, 0xA440 (VI base)
                        has_vi_reg = True
                if has_vi_reg:
                    return "osCreateViManager (candidate)"

    # jr ra as first instruction = stub function
    if is_jr_ra(instrs[0]):
        return "STUB (jr ra)"

    return None

def main():
    with open(ROM_PATH, "rb") as f:
        rom_data = f.read()

    # List of functions to check
    # Format: (vram, current_name, size)
    functions = [
        # Currently stubbed func_8008C* functions
        (0x8008C090, "func_8008C090", 0x70),
        (0x8008C100, "func_8008C100", 0x90),
        (0x8008C190, "func_8008C190", 0xF0),
        (0x8008C280, "func_8008C280", 0x110),
        (0x8008C390, "func_8008C390", 0x1C0),
        (0x8008C550, "osGetCount_8008C550", 0x220),
        (0x8008C770, "func_8008C770", 0x40),
        (0x8008C7B0, "func_8008C7B0", 0x180),
        (0x8008C930, "func_8008C930", 0x198),
        (0x8008CAC8, "func_8008CAC8", 0x664),
        (0x8008D42C, "func_8008D42C", 0xE4),
        (0x8008D510, "func_8008D510", 0x44),
        (0x8008D554, "func_8008D554", 0x54),
        (0x8008D5A8, "func_8008D5A8", 0x54),
        (0x8008D5FC, "func_8008D5FC", 0x88),
        (0x8008D684, "func_8008D684", 0xA8),
        (0x8008D72C, "func_8008D72C", 0x144),
        (0x8008D870, "func_8008D870", 0x440),
        (0x8008DCB0, "func_8008DCB0", 0xD0),
        (0x8008DD80, "func_8008DD80", 0x120),
        (0x8008DEA0, "func_8008DEA0", 0x174),
        (0x8008E074, "func_8008E074", 0x3AC),
        (0x8008E420, "func_8008E420", 0x12C),
        (0x8008E54C, "func_8008E54C", 0x4A8),
        (0x8008E9F4, "func_8008E9F4", 0xE8),
        (0x8008EADC, "func_8008EADC", 0x328),
        (0x8008EE04, "func_8008EE04", 0xE0),
        (0x8008EEE4, "func_8008EEE4", 0x1D0),
        (0x8008F0B4, "func_8008F0B4", 0x348),
        (0x8008F3FC, "func_8008F3FC", 0x584),
        (0x8008F980, "func_8008F980", 0x114),
        (0x8008FA94, "func_8008FA94", 0x8C),
        (0x8008FB20, "func_8008FB20", 0xAC),
        (0x8008FBCC, "func_8008FBCC", 0x194),
        (0x8008FC3C, "func_8008FC3C", 0x124),
        (0x8008FD60, "func_8008FD60", 0x8C),
        (0x8008FDEC, "func_8008FDEC", 0x74),
        (0x8008FE60, "func_8008FE60", 0x50),
        (0x8008FEB0, "func_8008FEB0", 0xE8),
        (0x8008FF98, "func_8008FF98", 0x148),
        (0x800900E0, "func_800900E0", 0x90),
        (0x80090170, "func_80090170", 0x90),
        (0x80090200, "func_80090200", 0xA0),
        (0x800902A0, "func_800902A0", 0x90),
        (0x80090330, "func_80090330", 0xA0),
        (0x800903D0, "func_800903D0", 0x80),
        (0x80090450, "func_80090450", 0x150),
        (0x800905A0, "func_800905A0", 0x58),
        (0x800905F8, "func_800905F8", 0x3C),
        (0x80090634, "func_80090634", 0x2C),
        (0x80090660, "func_80090660", 0x90),
        (0x800906F0, "func_800906F0", 0xE0),
        (0x80090880, "func_80090880", 0xE0),
        (0x80090960, "func_80090960", 0xB0),
        (0x80090A10, "func_80090A10", 0x210),
        (0x80090C20, "func_80090C20", 0x350),
        (0x80090F70, "func_80090F70", 0x164),
        (0x800910D4, "func_800910D4", 0x1AC),
        (0x80091280, "func_80091280", 0xD4),
        (0x80091354, "func_80091354", 0xAE0),
        (0x80091E34, "func_80091E34", 0x19C),
        (0x80091FD0, "func_80091FD0", 0x80),
        (0x80092050, "func_80092050", 0x510),
        (0x80092560, "func_80092560", 0x140),
        (0x800926A0, "func_800926A0", 0x270),
        (0x800928F0, "func_800928F0", 0x220),
        (0x80092B10, "func_80092B10", 0x670),
        (0x80093180, "func_80093180", 0x650),
        # Already named candidates:
        (0x800941E0, "osViManager_candidate", 0x300),
        (0x800944E0, "osPiStartDma_candidate_800944E0", 0xE0),
        (0x800945C0, "osPiManager_candidate_800945C0", 0x230),
        (0x80095820, "osPiStartDma_candidate_80095820", 0xBC),
        # Other funcs
        (0x80094C80, "func_80094C80", 0x1C4),
        (0x80094E44, "func_80094E44", 0x8C),
        (0x80094ED0, "func_80094ED0", 0x178),
        (0x80095048, "func_80095048", 0xAC),
        (0x800950F4, "func_800950F4", 0x1B8),
        (0x800952AC, "osPiManager_candidate_800952AC", 0x574),
        (0x800958DC, "func_800958DC", 0xB4),
        (0x80095990, "func_80095990", 0x1D8),
        (0x80095B68, "func_80095B68", 0xB8),
        (0x80095C20, "func_80095C20", 0x188),
        (0x80095DA8, "func_80095DA8", 0x18C),
        (0x80095F34, "func_80095F34", 0x228),
        (0x8009615C, "func_8009615C", 0x270),
        (0x800963CC, "func_800963CC", 0x3C4),
        (0x80096790, "func_80096790", 0x1A0),
        (0x80096930, "func_80096930", 0xD8),
        (0x80096A08, "func_80096A08", 0x1E8),
        (0x80096BF0, "func_80096BF0", 0x2A0),
        (0x80096E90, "func_80096E90", 0x570),
        (0x80097400, "func_80097400", 0x558),
    ]

    print("=" * 80)
    print("Libultra Function Identification")
    print("=" * 80)

    for vram, name, size in functions:
        result = identify_function(rom_data, vram, name, size)
        if result:
            print(f"  0x{vram:08X} ({name:40s} size=0x{size:04X}): {result}")

    # Also check for specific patterns at known sub-addresses
    print("\n" + "=" * 80)
    print("Sub-function patterns (packed functions)")
    print("=" * 80)

    # Check 0x8008C150 for osGetCount (inside func_8008C100)
    sub_checks = [
        (0x8008C150, "inside func_8008C100"),
        (0x8008C3B0, "inside func_8008C390"),
        (0x8008EA04, "inside func_8008E9F4"),
        (0x8008CA80, "inside func_8008C930"),
        (0x8008CAA0, "inside func_8008C930"),
        (0x8008D22C, "inside func_8008D42C+"),
    ]

    for vram, context in sub_checks:
        try:
            instrs = read_instructions(rom_data, vram, 8)
            result = identify_function(rom_data, vram, context, 32)

            # Print first few instructions
            instr_strs = []
            for instr in instrs[:4]:
                instr_strs.append(f"0x{instr:08X}")

            print(f"  0x{vram:08X} ({context:30s}): {result or 'unknown'}")
            print(f"    Instructions: {', '.join(instr_strs)}")
        except:
            pass

    # Detailed analysis of key addresses
    print("\n" + "=" * 80)
    print("Detailed JAL analysis for key functions")
    print("=" * 80)

    key_funcs = [
        (0x8008C100, "func_8008C100", 0x90),
        (0x8008C390, "func_8008C390", 0x1C0),
        (0x8008C550, "osGetCount_8008C550", 0x220),
        (0x8008E9F4, "func_8008E9F4", 0xE8),
        (0x80090170, "func_80090170", 0x90),
    ]

    for vram, name, size in key_funcs:
        n_instrs = size // 4
        instrs = read_instructions(rom_data, vram, n_instrs)
        jals = []
        for i, instr in enumerate(instrs):
            if is_jal(instr):
                t = jal_target(instr)
                jals.append(f"0x{t:08X}")
            if is_mfc0(instr):
                _, _, rt, rd, _, _, _, _ = decode_op(instr)
                jals.append(f"MFC0 r{rt},COP0_{rd}")
            if is_mtc0(instr):
                _, _, rt, rd, _, _, _, _ = decode_op(instr)
                jals.append(f"MTC0 r{rt},COP0_{rd}")
        print(f"  0x{vram:08X} {name}: calls={jals}")

if __name__ == "__main__":
    main()
