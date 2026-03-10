#!/usr/bin/env python3
"""
Star Wars Episode I: Racer - Recompilation Progress Tracker
==========================================================
Tracks how many functions have been identified, named, and verified.
Inspired by DKR decomp's score.sh system.

Usage: python tools/progress.py [symbols.toml]
"""

import sys
import os
import re
from datetime import datetime


def parse_symbols(path='symbols.toml'):
    """Parse symbols.toml and gather stats."""
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    functions = []
    current = {}

    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('name = "'):
                current['name'] = line.split('"')[1]
            elif line.startswith('vram = '):
                current['vram'] = int(line.split('=')[1].strip(), 16)
            elif line.startswith('size = '):
                current['size'] = int(line.split('=')[1].strip(), 16)
                if 'name' in current and 'vram' in current:
                    functions.append(current.copy())
                current = {}

    return functions


def calculate_progress(functions):
    """Calculate recompilation progress metrics."""
    total = len(functions)
    total_bytes = sum(f['size'] for f in functions)

    # A function is "named" if it doesn't follow the auto-generated pattern
    auto_pattern = re.compile(r'^func_[0-9A-Fa-f]{8}$')
    named = [f for f in functions if not auto_pattern.match(f['name'])]
    named_bytes = sum(f['size'] for f in named)

    # A function is "documented" if it has a descriptive name (not just a prefix)
    documented = [f for f in named if '_' in f['name'] and len(f['name']) > 10]
    documented_bytes = sum(f['size'] for f in documented)

    return {
        'total_funcs': total,
        'total_bytes': total_bytes,
        'named_funcs': len(named),
        'named_bytes': named_bytes,
        'documented_funcs': len(documented),
        'documented_bytes': documented_bytes,
    }


def print_progress_bar(label, current, total, width=40):
    """Print a fancy progress bar."""
    pct = current / total * 100 if total > 0 else 0
    filled = int(width * current / total) if total > 0 else 0
    bar = '#' * filled + '-' * (width - filled)
    print(f"  {label:20s} [{bar}] {pct:5.1f}% ({current}/{total})")


def main():
    symbols_path = sys.argv[1] if len(sys.argv) > 1 else 'symbols.toml'

    print()
    print("  ================================================")
    print("  =  SWE1R RECOMP - PROGRESS REPORT              =")
    print("  =  \"It's working! IT'S WORKING!\" - Anakin       =")
    print("  ================================================")
    print()
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    functions = parse_symbols(symbols_path)
    stats = calculate_progress(functions)

    print("  --- Function Progress ---")
    print_progress_bar("Discovered", stats['total_funcs'], stats['total_funcs'])
    print_progress_bar("Named", stats['named_funcs'], stats['total_funcs'])
    print_progress_bar("Documented", stats['documented_funcs'], stats['total_funcs'])

    print()
    print("  --- Byte Progress ---")
    total_kb = stats['total_bytes'] / 1024
    named_kb = stats['named_bytes'] / 1024
    print(f"  Total code:     {stats['total_bytes']:,} bytes ({total_kb:.1f} KB)")
    print(f"  Named code:     {stats['named_bytes']:,} bytes ({named_kb:.1f} KB)")
    print(f"  Named coverage: {stats['named_bytes']/stats['total_bytes']*100:.1f}%")

    # Size distribution
    print()
    print("  --- Function Size Distribution ---")
    size_buckets = {'tiny (<32B)': 0, 'small (32-128B)': 0,
                    'medium (128-512B)': 0, 'large (512B-2KB)': 0,
                    'huge (>2KB)': 0}
    for f in functions:
        if f['size'] < 32:
            size_buckets['tiny (<32B)'] += 1
        elif f['size'] < 128:
            size_buckets['small (32-128B)'] += 1
        elif f['size'] < 512:
            size_buckets['medium (128-512B)'] += 1
        elif f['size'] < 2048:
            size_buckets['large (512B-2KB)'] += 1
        else:
            size_buckets['huge (>2KB)'] += 1

    for label, count in size_buckets.items():
        print_progress_bar(label, count, stats['total_funcs'])

    # Top 10 largest functions
    print()
    print("  --- Top 10 Largest Functions ---")
    sorted_funcs = sorted(functions, key=lambda f: f['size'], reverse=True)
    for i, f in enumerate(sorted_funcs[:10]):
        print(f"  {i+1:2d}. {f['name']:30s} {f['size']:6,} bytes  (0x{f['vram']:08X})")

    print()
    print("  May the Force guide your reverse engineering.")
    print()


if __name__ == '__main__':
    main()
