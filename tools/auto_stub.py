#!/usr/bin/env python3
"""
Auto-stub helper: Iteratively runs N64Recomp, detects failing static_0_*
functions (COP0/CACHE errors), and adds them to the stubs list in recomp.toml.
"""
import subprocess
import sys
import re

RECOMP_EXE = r"D:\recomp\n64\N64Recomp\build\Release\N64Recomp.exe"
TOML_PATH = "recomp.toml"
MAX_ITERATIONS = 200

def get_current_stubs(toml_text):
    """Extract the stubs list from recomp.toml."""
    match = re.search(r'stubs\s*=\s*\[(.*?)\]', toml_text, re.DOTALL)
    if not match:
        return []
    content = match.group(1)
    return re.findall(r'"([^"]+)"', content)

def run_recomp():
    """Run N64Recomp and return (success, failing_func_name)."""
    result = subprocess.run(
        [RECOMP_EXE, TOML_PATH],
        capture_output=True, text=True, cwd="."
    )
    output = result.stdout + result.stderr

    # Look for error pattern
    match = re.search(r'Error recompiling (\S+)', output)
    if match:
        return False, match.group(1), output

    # Check for success indicators
    if "Function count:" in output and "Error" not in output:
        return True, None, output

    # Also check return code
    if result.returncode == 0:
        return True, None, output

    return False, None, output

def add_stub(func_name):
    """Add a function to the stubs list in recomp.toml."""
    with open(TOML_PATH, 'r') as f:
        content = f.read()

    # Find the last entry in the stubs array and add after it
    # Look for the last quoted string before the closing ]
    # The stubs array ends with: "func_name",\n]
    pattern = re.compile(r'(stubs\s*=\s*\[.*?"[^"]+",?\s*)\n(\])', re.DOTALL)
    match = pattern.search(content)
    if not match:
        print(f"ERROR: Could not find stubs array in {TOML_PATH}")
        sys.exit(1)

    before = match.group(1).rstrip()
    # Ensure trailing comma on last entry
    if not before.endswith(','):
        before += ','
    new_content = before + '\n    "' + func_name + '",\n' + match.group(2)
    content = content[:match.start()] + new_content + content[match.end():]

    with open(TOML_PATH, 'w') as f:
        f.write(content)

def main():
    added = []
    for i in range(MAX_ITERATIONS):
        print(f"\n--- Iteration {i+1} ---")
        success, failing_func, output = run_recomp()

        if success:
            print(f"\nSUCCESS! N64Recomp completed successfully.")
            print(f"Added {len(added)} stubs: {added}")
            return 0

        if failing_func is None:
            print(f"Unknown error:\n{output[-500:]}")
            return 1

        print(f"  Failed on: {failing_func}")

        # Only auto-add static_0_* functions
        if not failing_func.startswith("static_0_"):
            print(f"  Non-static function failed. Need manual intervention.")
            print(f"  Output:\n{output[-500:]}")
            return 1

        add_stub(failing_func)
        added.append(failing_func)
        print(f"  Added to stubs. Total added: {len(added)}")

    print(f"Hit max iterations ({MAX_ITERATIONS})")
    return 1

if __name__ == "__main__":
    sys.exit(main())
