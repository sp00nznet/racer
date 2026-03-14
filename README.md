# Star Wars Episode I: Racer - N64 Static Recompilation

```
    ____________________________
   /  ________________________  \
  /  /  ___________________  \  \
 /  /  / ___ _    _ ____ _ \ \  \
|  |  | / __| |  | |  __/ | |  |  |
|  |  | \__ \ |/\| | |__  | |  |  |     "Now THIS is podracing!"
|  |  | |___/\    /|____|_| |  |  |          - Anakin Skywalker
|  |  |  ___ _  _ ___ __   |  |  |
|  |  | | __| \/ | _ /  \  |  |  |
|  |  | | _||  . |  /  __|_|  |  |
|  |  | |___|_/\_|_| \___| |  |  |
 \  \  \___________________/  /  /
  \  \________________________/  /
   \____________________________/
```

## What is this?

This is a **static recompilation** project for *Star Wars Episode I: Racer* on the Nintendo 64, using [N64Recomp](https://github.com/N64Recomp/N64Recomp). The goal: take the original N64 binary and recompile it into native PC code, so you can podrace at modern resolutions and framerates without emulation.

No existing N64 decompilation exists for this game. We're flying blind through Beggar's Canyon here, folks.

## Status

| Milestone | Status |
|-----------|--------|
| ROM Analysis | COMPLETE |
| Function Discovery (878+ functions) | COMPLETE |
| Symbol File Generation | COMPLETE |
| N64Recomp Config | COMPLETE |
| Debug Tooling (analyzer, differ, strings, progress) | COMPLETE |
| Build System (Make + CMake) | COMPLETE |
| libultra Stubbing (~120 functions) | COMPLETE |
| N64Recomp Integration | COMPLETE |
| **Native Compilation (MSVC)** | **COMPLETE** |
| **N64ModernRuntime Integration** | **COMPLETE** |
| **libultra Function Identification (21 reimplemented)** | **COMPLETE** |
| **Game Boot + Stable Execution** | **COMPLETE** |
| **RSP Task Routing (osSpTaskLoad/StartGo)** | **COMPLETE** |
| **osRecvMesg Thread Blocking Fix** | **IN PROGRESS** |
| **RT64 Renderer Integration** | **IN PROGRESS** |
| **SDL2 Window + Input** | **IN PROGRESS** |
| Display List Rendering | IN PROGRESS |
| Audio Reimplementation | TODO |
| Playable Build | THE DREAM |

**Current Progress: Phase 4 - RSP Task Routing & Thread Fix**

*"I've got a bad feeling about this." - Everyone, debugging thread scheduling*

The game **boots and runs without crashing**. RSP task submission has been identified and routed through ultramodern's `submit_rsp_task` for RT64 rendering. A critical thread blocking bug was found: the game's real `osRecvMesg` was misidentified, causing the scheduler thread (priority 254) to spin-lock and starve all other game threads. Fix is in progress.

- **1,381 functions** in the lookup table (878 symbols + ~500 auto-detected statics)
- **21 libultra functions** identified and reimplemented via ultramodern:
  - **NEW**: `osSpTaskLoad`, `osSpTaskStartGo` — game's custom RSP task loader identified and redirected
  - **NEW**: `osRecvMesg` — game's REAL osRecvMesg found at 0x80087E80 (not the unused copy at 0x8008C3B0)
  - Plus: osCreateThread, osCreateMesgQueue, osSendMesg, osViSetMode, osPiStartDma, and more
- **RSP task flow decoded**: game bypasses standard `osSpTaskLoad` — uses custom implementation with raw SP DMA (`__osSpRawStartDma`), now intercepted
- **Thread starvation bug found**: scheduler thread blocked forever on game's custom osRecvMesg (stubbed yield function = infinite spin at priority 254)
- **PI handle initialization** replicated for stubbed boot code (COP0 exception handlers)
- **SWE1Racer.exe** links against N64ModernRuntime (librecomp + ultramodern) + RT64
- RT64 renderer initialized (D3D12 backend, RTX 5070 detected)
- SDL2 window (1280x960), keyboard input, and event loop running
- Audio frequency set to 48kHz (playback stubs - Phase 5 TODO)
- Linker MAP file generation for crash debugging
- Built with MSVC (Visual Studio 2022) and CMake

## ROM Info

| Field | Value |
|-------|-------|
| Title | STAR WARS EP1 RACER |
| Game Code | NEPE |
| Region | USA (NTSC) |
| Entry Point | 0x80000400 |
| CRC1 | 0x72F70398 |
| CRC2 | 0x6556A98B |
| ROM Size | 32 MB |
| Code Size | ~608 KB (0x1000 - 0x99000) |
| Functions | 878 symbols + ~540 auto-detected |

## Getting Started

### Prerequisites

- Python 3.x
- GNU Make (or compatible)
- [N64Recomp](https://github.com/N64Recomp/N64Recomp) (for recompilation step)
- Your own legally obtained ROM: `Star Wars Episode I - Racer (U) [!].z64`

### Setup

```bash
# Clone the repo
git clone https://github.com/sp00nznet/racer.git
cd racer

# Place your ROM in the project root
cp /path/to/your/rom.z64 baserom.z64

# Run initial analysis
make

# Check progress
make progress
```

### Debug Tools

We've got a full pit crew of analysis tools, inspired by the DKR decompilation project:

```bash
# Analyze the ROM structure and regenerate symbols
make analyze

# Disassemble any function
make diff FUNC=func_80000470

# Dump all strings from the ROM
make strings

# Just the debug strings (source files, asserts, etc.)
make strings-debug

# Game text (menus, dialogue, taunts from Sebulba)
make strings-game

# File paths referenced in the ROM
make strings-files

# View recompilation progress
make progress
```

### Building

```bash
# 1. Build N64Recomp (the recompiler tool)
cd /path/to/N64Recomp
cmake -B build -G "Visual Studio 17 2022"
cmake --build build --config Release --target N64RecompCLI

# 2. Recompile the game (MIPS -> C)
cd /path/to/racer
make recomp N64RECOMP=/path/to/N64Recomp/build/Release/N64Recomp.exe

# 3. Generate the function lookup table
python tools/gen_lookup_table.py

# 4. Build the native executable
cmake -B build -G "Visual Studio 17 2022"
cmake --build build --config Release

# 5. Run it!
build/Release/SWE1Racer.exe
```

## Project Structure

```
racer/
├── README.md              # You are here
├── Makefile               # Analysis & debug build system
├── CMakeLists.txt         # CMake build for native executable
├── recomp.toml            # N64Recomp configuration
├── symbols.toml           # Function symbols (878 functions, 17 libultra identified)
├── baserom.z64            # Your ROM goes here (not tracked)
├── tools/
│   ├── rom_analyzer.py    # ROM analysis & symbol generation
│   ├── func_differ.py     # Function disassembler
│   ├── string_dumper.py   # String extraction & categorization
│   ├── progress.py        # Progress tracker
│   ├── identify_libultra.py # libultra function pattern matcher (MIPS instruction matching)
│   ├── fix_statics.py     # Auto-fix static_0_ sub-function errors
│   └── gen_lookup_table.py # Generate function lookup table
├── src/
│   ├── main.cpp           # Entry point, SDL window, callbacks
│   ├── section_table.cpp  # VRAM->function pointer lookup table
│   ├── rt64_render_context.cpp  # RT64 renderer bridge (placeholder)
│   └── audio.cpp          # Audio stubs (SDL playback TODO)
├── RecompiledFuncs/       # N64Recomp output (generated)
│   ├── funcs.h            # Function declarations
│   └── funcs_*.c          # Recompiled C code (29 files)
├── include/               # Project headers
└── build/                 # CMake build output
```

## Fun Stuff Found in the ROM

The developers at LucasArts left some gems in the binary:

- **Developer control schemes**: "---Jonk---", "---Jake---", "---Steve---", "---Alex---", "---Brett Sett---" - each dev had their own controller config!
- **Debug menu**: `Debug Level`, `Edit Vehicle Stats`, `AI Level x10` - there's a full debug menu hiding in there
- **Sebulba trash talk**: *"I could run faster than your podracer"*, *"Watto sell you that podracer?"*
- **Cheat codes**: `All Pods, tracks unlocked!!!`
- **Engine fire**: `ENGINE FIRE` - every podracer's nightmare
- **Low memory warning**: `Low Memory: %d Racers` - when the N64 couldn't handle all those pods

## How N64 Static Recompilation Works

```
  N64 ROM (MIPS)
       |
       v
  [N64Recomp] -----> Reads symbols.toml for function boundaries
       |
       v
  Recompiled C code (one file per ~50 functions)
       |
       v
  [C Compiler] + [N64ModernRuntime] (reimplements libultra)
       |
       v
  Native PC executable!
```

Unlike emulation, static recompilation converts every MIPS instruction into equivalent C code at build time. The result runs natively on your CPU - no instruction-by-instruction interpretation needed. This means better performance, easier modding, and native resolution/widescreen support.

## References & Credits

- [N64Recomp](https://github.com/N64Recomp/N64Recomp) - The static recompiler that makes this possible
- [Zelda64Recomp](https://github.com/Zelda64Recomp/Zelda64Recomp) - The project that proved N64 recomp works
- [Diddy Kong Racing Decomp](https://github.com/DavidSM64/Diddy-Kong-Racing) - Debug tooling inspiration
- [N64ModernRuntime](https://github.com/N64Recomp/N64ModernRuntime) - Runtime library for recompiled games
- [OpenSWE1R](https://github.com/OpenSWE1R) - PC version reverse engineering (different codebase, but useful reference)
- [SW_RACER_RE](https://github.com/tim-tim707/SW_RACER_RE) - PC version decompilation

## Legal

This project does not include any copyrighted material. You must provide your own legally obtained ROM. Star Wars Episode I: Racer is a trademark of Lucasfilm Ltd.

---

*"I have a bad feeling about this." - Everyone in Star Wars, at some point*

*"It's working! IT'S WORKING!" - What we said when the game booted (now we need the first frame to render)*

*"Your focus determines your reality." - Qui-Gon Jinn (also good advice for debugging recompiled MIPS)*
