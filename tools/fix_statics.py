#!/usr/bin/env python3
"""
Iteratively fix static_0_* auto-detection errors by:
1. Running N64Recomp
2. When a static_0_XXXXXXXX error occurs, find its parent function in symbols.toml
3. Split the parent to create an explicit function at that address
4. Add the new function to the stubs list in recomp.toml
5. Repeat until success
"""
import subprocess
import sys
import re
import struct

RECOMP_EXE = r"D:\recomp\n64\N64Recomp\build\Release\N64Recomp.exe"
TOML_PATH = "recomp.toml"
SYMBOLS_PATH = "symbols.toml"
ROM_PATH = "baserom.z64"
MAX_ITERATIONS = 100

# Section info from symbols.toml
SECTION_ROM = 0x1000
SECTION_VRAM = 0x80000400

def read_rom_word(rom_data, vram):
    """Read a 32-bit word from ROM at the given VRAM address."""
    rom_offset = vram - SECTION_VRAM + SECTION_ROM
    return struct.unpack('>I', rom_data[rom_offset:rom_offset+4])[0]

def find_parent_function(symbols_text, target_vram):
    """Find the function that contains the target VRAM address."""
    pattern = re.compile(
        r'\[\[section\.functions\]\]\s*\n\s*name\s*=\s*"([^"]+)"\s*\n\s*vram\s*=\s*(0x[0-9A-Fa-f]+)\s*\n\s*size\s*=\s*(0x[0-9A-Fa-f]+)',
        re.MULTILINE
    )
    best_match = None
    for m in pattern.finditer(symbols_text):
        name = m.group(1)
        vram = int(m.group(2), 16)
        size = int(m.group(3), 16)
        if vram <= target_vram < vram + size:
            if best_match is None or vram > best_match[1]:
                best_match = (name, vram, size, m.start(), m.end())
    return best_match

def find_next_function_vram(symbols_text, after_vram):
    """Find the next function's VRAM address after the given address."""
    pattern = re.compile(r'vram\s*=\s*(0x[0-9A-Fa-f]+)')
    vrams = sorted(set(int(m.group(1), 16) for m in pattern.finditer(symbols_text)))
    for v in vrams:
        if v > after_vram:
            return v
    return None

def split_function(symbols_text, parent_name, parent_vram, parent_size, target_vram, new_func_name):
    """Split a parent function at target_vram, creating a new function."""
    old_size_hex = f"0x{parent_size:X}"
    new_parent_size = target_vram - parent_vram
    new_func_size = parent_size - new_parent_size
    new_parent_size_hex = f"0x{new_parent_size:X}"
    new_func_size_hex = f"0x{new_func_size:X}"

    old_block = (
        f'  [[section.functions]]\n'
        f'  name = "{parent_name}"\n'
        f'  vram = 0x{parent_vram:08X}\n'
        f'  size = {old_size_hex}'
    )

    new_block = (
        f'  [[section.functions]]\n'
        f'  name = "{parent_name}"\n'
        f'  vram = 0x{parent_vram:08X}\n'
        f'  size = {new_parent_size_hex}\n'
        f'\n'
        f'  # Auto-split from {parent_name} to prevent static_0_ detection\n'
        f'  [[section.functions]]\n'
        f'  name = "{new_func_name}"\n'
        f'  vram = 0x{target_vram:08X}\n'
        f'  size = {new_func_size_hex}'
    )

    if old_block not in symbols_text:
        # Try with lowercase hex in size
        old_size_hex_lower = f"0x{parent_size:x}"
        old_block = (
            f'  [[section.functions]]\n'
            f'  name = "{parent_name}"\n'
            f'  vram = 0x{parent_vram:08X}\n'
            f'  size = {old_size_hex_lower}'
        )
        if old_block not in symbols_text:
            print(f"  WARNING: Could not find exact block for {parent_name} at 0x{parent_vram:08X}")
            print(f"  Looking for:\n{old_block}")
            return None

    return symbols_text.replace(old_block, new_block, 1)

def add_stub(recomp_text, func_name):
    """Add a function to the stubs list in recomp.toml."""
    # Find the last entry before ]
    pattern = re.compile(r'(stubs\s*=\s*\[.*?"[^"]+",?)\s*\n(\])', re.DOTALL)
    match = pattern.search(recomp_text)
    if not match:
        print(f"ERROR: Could not find stubs array")
        return None

    before = match.group(1).rstrip()
    if not before.endswith(','):
        before += ','
    return recomp_text[:match.start()] + before + f'\n    "{func_name}",\n' + match.group(2) + recomp_text[match.end():]

def run_recomp():
    """Run N64Recomp and return (success, error_func, error_type, output)."""
    result = subprocess.run(
        [RECOMP_EXE, TOML_PATH],
        capture_output=True, text=True, cwd="."
    )
    output = result.stdout + result.stderr

    # Check for static function errors
    match = re.search(r'Error recompiling (static_0_[0-9A-Fa-f]+)', output)
    if match:
        return False, match.group(1), "static", output

    # Check for other recompilation errors
    match = re.search(r'Error recompiling (\S+)', output)
    if match:
        return False, match.group(1), "other", output

    # Check for non-existent stub/patch errors
    match = re.search(r'Function (\S+) is stubbed.*does not exist', output)
    if match:
        return False, match.group(1), "stub_not_found", output

    match = re.search(r'Function (\S+) has an instruction patch.*does not exist', output)
    if match:
        return False, match.group(1), "patch_not_found", output

    if result.returncode == 0:
        return True, None, None, output

    return False, None, "unknown", output

def main():
    added_funcs = []

    for iteration in range(MAX_ITERATIONS):
        print(f"\n=== Iteration {iteration + 1} ===")
        success, error_func, error_type, output = run_recomp()

        if success:
            print(f"\nSUCCESS! N64Recomp completed successfully!")
            print(f"Added {len(added_funcs)} functions: {added_funcs}")
            return 0

        if error_type != "static":
            print(f"Non-static error ({error_type}): {error_func}")
            # Print last few lines for context
            lines = output.strip().split('\n')
            for line in lines[-10:]:
                print(f"  {line}")
            return 1

        # Parse the VRAM address from static_0_XXXXXXXX
        match = re.match(r'static_0_([0-9A-Fa-f]+)', error_func)
        if not match:
            print(f"Could not parse address from {error_func}")
            return 1

        target_vram = int(match.group(1), 16)
        print(f"  Static function at 0x{target_vram:08X}")

        # Read current symbols
        with open(SYMBOLS_PATH, 'r') as f:
            symbols_text = f.read()

        # Find parent function
        parent = find_parent_function(symbols_text, target_vram)
        if parent is None:
            print(f"  No parent function found for 0x{target_vram:08X}")
            # The address might not be in any defined function - need to add a new one
            # Find the nearest function before this address
            pattern = re.compile(r'vram\s*=\s*(0x[0-9A-Fa-f]+)')
            vrams = sorted(set(int(m.group(1), 16) for m in pattern.finditer(symbols_text)))
            prev_vram = max(v for v in vrams if v < target_vram)
            next_vram = min(v for v in vrams if v > target_vram)
            print(f"  Between functions at 0x{prev_vram:08X} and 0x{next_vram:08X}")
            print(f"  Need manual intervention")
            return 1

        parent_name, parent_vram, parent_size, _, _ = parent
        new_func_name = f"libultra_split_{target_vram:08X}"
        print(f"  Parent: {parent_name} (0x{parent_vram:08X}, size 0x{parent_size:X})")
        print(f"  Creating: {new_func_name}")

        # Split the function in symbols.toml
        new_symbols = split_function(symbols_text, parent_name, parent_vram, parent_size, target_vram, new_func_name)
        if new_symbols is None:
            return 1

        with open(SYMBOLS_PATH, 'w') as f:
            f.write(new_symbols)

        # Add the new function to stubs in recomp.toml
        with open(TOML_PATH, 'r') as f:
            recomp_text = f.read()

        new_recomp = add_stub(recomp_text, new_func_name)
        if new_recomp is None:
            return 1

        with open(TOML_PATH, 'w') as f:
            f.write(new_recomp)

        added_funcs.append(new_func_name)
        print(f"  Done. Total splits: {len(added_funcs)}")

    print(f"Hit max iterations ({MAX_ITERATIONS})")
    return 1

if __name__ == "__main__":
    sys.exit(main())
