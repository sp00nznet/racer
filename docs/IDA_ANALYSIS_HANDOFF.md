# IDA Pro Cross-Validation — SW Episode I: Racer (N64)

Headless IDA Pro 9.1 analysis of `baserom.z64`, loaded at the recomp's exact vram
and cross-checked against `symbols.toml` / `recomp.toml`.

**Load recipe** (`idat.exe`, since idalib can't do non-default loaders):
```
idat.exe -A -Tbinary -pmipsb -b0x7FFFF40 -S"n64_analyze.py <proj> <out>" baserom.z64
```
Single code section, rom→vram delta `0x7FFFF400`. R4300 ⇒ code segments must be
64-bit so Hex-Rays uses the MIPS64 decompiler.

## Result: `symbols.toml` is flawless ✅

| Check | Result |
|---|---|
| Functions seeded into IDA | **880 / 880** |
| Missed functions (prologue in gap) | **0** |
| IDA-only functions in code section | **0** — IDA's independent analysis agrees exactly |
| Boundary layout | 879 contiguous, 1 trailing padding |

IDA independently reproduced the recomp's function table to the function — the
cleanest result of all projects checked. **No action required.**

## Deliverable: aligned reference pseudocode
`E:\ida\work\podracer\decomp\_podracer_reference.c` (~76 KB) — Hex-Rays MIPS64
decompilation of the 15 largest functions + 5 stubs, addresses matching the recomp.
Regenerate with `E:\ida\tools\n64_analyze.py`.
