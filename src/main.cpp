// Star Wars Episode I: Racer - N64 Static Recompilation
// Main entry point
//
// "Now THIS is podracing!" - Anakin Skywalker

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>
#include <algorithm>
#include <fstream>
#include <sstream>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dbghelp.h>
#include <tlhelp32.h>
#endif
#include <thread>

#include <SDL.h>

#include "recomp.h"
#include "librecomp/game.hpp"
#include "librecomp/overlays.hpp"
#include "librecomp/rsp.hpp"
#include "librecomp/addresses.hpp"
#include "ultramodern/ultramodern.hpp"
#include "ultramodern/ultra64.h"
#include "ultramodern/renderer_context.hpp"
#include "ultramodern/error_handling.hpp"
#include "ultramodern/events.hpp"
#include "ultramodern/input.hpp"
#include "ultramodern/threads.hpp"
#include "frontend/frontend.hpp"

// =============================================================================
// External declarations
// =============================================================================

// From section_table.cpp
extern SectionTableEntry section_table[];
extern const size_t num_sections;

// The recompiled entrypoint function
extern "C" void recomp_entrypoint(uint8_t* rdram, recomp_context* ctx);

// libultra's audio microcode, recompiled from the ROM by RSPRecomp (rsp/aspMain.toml)
extern RspUcodeFunc aspMain;

// RDRAM base — captured in on_game_init so the crash handler can translate
// native fault addresses back into N64 virtual addresses.
static uint8_t* g_rdram_base = nullptr;

// SI DMA: the game's __osSiRawStartDma is COP0/MMIO based and can't be
// recompiled. It moves a 64-byte block between DRAM and PIF RAM and raises an
// SI interrupt on completion.
//
//   a0 = direction (1 = DRAM->PIF write, 0 = PIF->DRAM read)
//   a1 = DRAM buffer address
//
// There is no PIF hardware here, so on a read we synthesize the controller
// status block the game's detection code (func_800899E8) expects: 8 bytes per
// channel, 4 channels. Controller 0 is reported present (standard pad, no pak);
// channels 1-3 report "no controller" via the error bits in byte 2.
//   byte0 pad | byte1 txsize | byte2 rxsize/error | byte3 cmd
//   byte4 type_lo | byte5 type_hi | byte6 status | byte7 pad
// The parser checks (byte2 & 0xC0) for an error, reads type from byte4/5 and
// the pak/status flag from byte6.
extern "C" void __osSiRawStartDma_recomp(uint8_t* rdram, recomp_context* ctx) {
    int32_t  dir = (int32_t)ctx->r4;
    uint32_t buf = (uint32_t)ctx->r5;

    if (dir == 0 && buf != 0) {
        // PIF -> DRAM read: fill in the controller status response.
        // The block is word-aligned, so big-endian-packed word writes land the
        // bytes correctly for the recompiled MEM_B (XOR 3) accessors.
        auto w32 = [&](uint32_t addr, uint32_t value) {
            *(uint32_t*)(rdram + (addr - 0x80000000u)) = value;
        };
        for (int ch = 0; ch < 4; ch++) {
            uint32_t c = buf + ch * 8;
            if (ch == 0) {
                w32(c + 0, 0xFF010300u); // pad, tx=1, rx=3 (no error), cmd=0
                w32(c + 4, 0x050000FFu); // type=0x0005 (standard pad), no pak
            } else {
                w32(c + 0, 0xFF018300u); // byte2=0x83 -> error bit set
                w32(c + 4, 0xFFFFFFFFu); // no controller on this channel
            }
        }
        printf("[si] __osSiRawStartDma read  -> controller status written to 0x%08X\n", buf);
    } else {
        // Log each distinct PIF command block once (debug: which SI devices the game talks to).
        static std::vector<std::string> seen;
        char hex[64 * 2 + 1];
        for (int i = 0; i < 64; i++) {
            snprintf(hex + i * 2, 3, "%02X", rdram[((buf + i) ^ 3) - 0x80000000u]);
        }
        if (std::find(seen.begin(), seen.end(), hex) == seen.end()) {
            seen.push_back(hex);
            printf("[si] PIF write ra=0x%08X: %s\n", (uint32_t)ctx->r31, hex);
        }
    }

    // No real hardware to wait on — signal SI completion immediately.
    ultramodern::send_si_message();
    ctx->r2 = 0; // success
}

// =============================================================================
// ROM Hash: Star Wars Episode I: Racer (US)
// CRC1: 0x72F70398  CRC2: 0x6556A98B
// =============================================================================
constexpr uint64_t SWE1R_ROM_HASH = 0x9B89D0F9EBC12D32ULL; // XXH3_64bits of baserom.z64

// =============================================================================
// RSP Callbacks
// =============================================================================

// No-op RSP microcode. We don't yet have SWE1R's recompiled audio microcode
// (that would come from N64Recomp's RSPRecomp, like pokemonsnap's aspMain).
// Returning nullptr makes ultramodern's run_task abort the whole process, so
// instead we pretend audio tasks completed (RspExitReason::Broke). Result: no
// sound yet, but the game proceeds — and graphics tasks (M_GFXTASK) never reach
// here anyway; submit_rsp_task routes those straight to the RT64 renderer.
static RspExitReason swe1r_noop_ucode(uint8_t* /*rdram*/, uint32_t /*ucode_addr*/) {
    return RspExitReason::Broke;
}

RspUcodeFunc* get_rsp_microcode(const OSTask* task) {
    static uint32_t rsp_call_count = 0;
    rsp_call_count++;
    if (rsp_call_count <= 5 || (rsp_call_count % 120 == 0)) {
        fprintf(stderr, "[SWE1R] get_rsp_microcode #%u: type=%u ucode=0x%08X data=0x%08X\n",
                rsp_call_count, task->t.type,
                (uint32_t)task->t.ucode, (uint32_t)task->t.ucode_data);
    }
    // Graphics tasks go straight to RT64; audio tasks run the recompiled aspMain.
    if (task->t.type == M_AUDTASK) return aspMain;
    return swe1r_noop_ucode;
}

// =============================================================================
// Event Callbacks
// =============================================================================


void vi_callback() {
    // Called every VI interrupt
}

// The game's osGetCount (racer_osGetCount, redirected by tools/post_recomp_patches.py). The runtime
// returns virtual time in deterministic mode.
extern "C" void racer_get_count(uint8_t* rdram, recomp_context* ctx) {
    ctx->r2 = (int32_t)osGetCount(); // mfc0 sign-extends
}

// =============================================================================
// Thread Naming
// =============================================================================

std::string get_game_thread_name(const OSThread* t) {
    return "SWE1R-Thread";
}

// =============================================================================
// Game Init Callback - initialize libultra state that stubbed boot code skips
// =============================================================================

void on_game_init(uint8_t* rdram, recomp_context* ctx) {
    // Capture the RDRAM base so the crash handler can map native fault
    // addresses back to N64 virtual addresses.
    g_rdram_base = rdram;
    fe::set_rdram(rdram);

    // The game's boot code at 0x8008D284 initializes the PI (cartridge ROM) handle
    // and stores it at globals 0x800A7BC0 and 0x800A7FC0. That code is stubbed
    // because it contains COP0 instructions. We replicate the initialization here.

    // Initialize the PI handle struct at the pre-allocated RDRAM address
    int32_t handle_addr = recomp::cart_handle; // 0x80800000
    OSPiHandle* handle = (OSPiHandle*)(rdram + ((uint32_t)handle_addr - 0x80000000u));
    memset(handle, 0, sizeof(OSPiHandle));
    handle->type = 0; // PI_DOMAIN2 (cartridge)
    handle->baseAddress = 0xB0000000; // phys_to_k1(0x10000000) = cartridge ROM base
    handle->domain = 0;

    // Store the handle pointer in the game's global variables (big-endian u32 writes)
    // 0x800A7BC0 = __osCartRomHandle (used by PI access functions)
    // 0x800A7FC0 = __osPiTable (PI device linked list head)
    auto write32 = [&](uint32_t mips_addr, uint32_t value) {
        *(uint32_t*)(rdram + (mips_addr - 0x80000000u)) = value;
    };

    write32(0x800A7BC0, (uint32_t)handle_addr);
    write32(0x800A7FC0, (uint32_t)handle_addr);

    // Self-link the handle's next pointer (linked list of one element)
    // handle_addr = 0x80800000, so this writes to RDRAM offset 0x00800000 (8MB)
    write32((uint32_t)handle_addr, (uint32_t)handle_addr); // handle->unused (next ptr) = self

    printf("[SWE1R] PI handle initialized at 0x%08X\n", (uint32_t)handle_addr);

    // Initialize VI state for the scheduler thread.
    // The scheduler (func_8008BC30) calls static_0_800941D0 which reads a pointer
    // from 0x800A7F50 pointing to the "current VI mode" struct. It uses:
    //   +0x02 (halfword): retrace count — how many VI retraces before sending a response
    //   +0x10 (word): response queue — where to send the "frame done" message
    // osCreateViManager normally sets this up, but it's stubbed in the recomp.
    // Without this, the scheduler sends responses to its own queue (feedback loop)
    // and never yields to the game thread.
    //
    // We create a fake VI state at 0x800A7F00 (unused BSS near the pointer) and a
    // "sink" queue at 0x800A7E80 that absorbs the scheduler's responses.

    // Create the sink queue: osCreateMesgQueue(queue=0x800A7E80, buf=0x800A7E60, count=8)
    // We can't call osCreateMesgQueue_recomp here (no ctx), so write the struct directly.
    // OSMesgQueue layout (big-endian):
    //   +0x00: mtqueue (PTR) = 0 (unused)
    //   +0x04: fullqueue (PTR) = 0 (unused)
    //   +0x08: validCount (s32) = 0
    //   +0x0C: first (s32) = 0
    //   +0x10: msgCount (s32) = 8
    //   +0x14: msg (PTR) = 0x800A7E60 (buffer)
    write32(0x800A7E80 + 0x00, 0);
    write32(0x800A7E80 + 0x04, 0);
    write32(0x800A7E80 + 0x08, 0);
    write32(0x800A7E80 + 0x0C, 0);
    write32(0x800A7E80 + 0x10, 8);
    write32(0x800A7E80 + 0x14, 0x800A7E60);

    // Create fake VI state at 0x800A7F00
    // RDRAM uses native word order with XOR byte-swapping for sub-word access.
    // MEM_W reads/writes uint32_t directly. MEM_HU(0x02, base) reads the lower
    // halfword of the word at base. So to set the halfword at +0x02 = 1,
    // we write the word at +0x00 = 0x00000001 (lower half = 1, upper half = 0).
    memset(rdram + (0x800A7F00 - 0x80000000u), 0, 0x20);
    write32(0x800A7F00, 0x00000001);  // +0x00 word: lower halfword (+0x02) = retrace count 1
    write32(0x800A7F10, 0x800A7E80);  // +0x10: response queue = sink queue

    // Point the VI state pointer to our struct
    write32(0x800A7F50, 0x800A7F00);
    printf("[SWE1R] VI state initialized at 0x800A7F00, sink queue at 0x800A7E80\n");

    // osMemSize at 0x80000318 — IPL3 normally writes the detected RDRAM size
    // here, but we stub IPL3. SWE1R requires the Expansion Pak, so report 8MB.
    // The framebuffer allocator (func_80039A38) reads this to size buffers.
    // 0x318 is below the game's BSS clear (0x520+), so this value survives;
    // the framebuffer pointer table at 0x80114530 must NOT be seeded here, as
    // it sits inside the cleared range and is populated by func_80039A38.
    write32(0x80000318, 0x00800000);
    printf("[SWE1R] osMemSize=0x800000 written at 0x80000318\n");
}

// The debugging aids below (crash traces, SWE1R_STACKDUMP, SWE1R_WATCH) use DbgHelp and
// Win32 thread contexts, so they are Windows only.
#ifdef _WIN32
// =============================================================================
// Map-file symbolizer
//
// Release builds have no useful PDB symbols for the recompiled funcs (SymFromAddr
// returns garbage like "wcsrchr"). The linker .map file, however, lists every
// func_XXXX with its preferred VA. We parse it at startup and resolve crash
// stack frames against it — automating the manual map lookup used during Phase 5.
// =============================================================================
struct MapSym { uint32_t rva; std::string name; };
static std::vector<MapSym> g_map_syms;
static constexpr uint64_t MAP_PREFERRED_BASE = 0x140000000ull;

static bool is_hex16_va(const std::string& s) {
    if (s.size() != 16 || s.compare(0, 10, "0000000140") != 0) return false;
    for (char c : s) if (!isxdigit((unsigned char)c)) return false;
    return true;
}

static void load_map_symbols() {
    char exePath[MAX_PATH];
    GetModuleFileNameA(NULL, exePath, MAX_PATH);
    std::filesystem::path mapPath = std::filesystem::path(exePath).replace_extension(".map");
    std::ifstream f(mapPath);
    if (!f) {
        fprintf(stderr, "[map] no symbol map at %s (crash traces won't be symbolized)\n",
                mapPath.string().c_str());
        return;
    }
    std::string line;
    while (std::getline(f, line)) {
        // Symbol lines look like: " 0001:00025e00   <name>   0000000140026e00 f i x.obj"
        std::istringstream iss(line);
        std::vector<std::string> tok;
        for (std::string t; iss >> t; ) tok.push_back(t);
        if (tok.size() < 3) continue;
        // tok[0] must be SECTION:OFFSET
        if (tok[0].size() != 13 || tok[0][4] != ':') continue;
        for (size_t i = 2; i < tok.size(); i++) {
            if (is_hex16_va(tok[i])) {
                uint64_t va = strtoull(tok[i].c_str(), nullptr, 16);
                g_map_syms.push_back({ (uint32_t)(va - MAP_PREFERRED_BASE), tok[i - 1] });
                break;
            }
        }
    }
    std::sort(g_map_syms.begin(), g_map_syms.end(),
              [](const MapSym& a, const MapSym& b) { return a.rva < b.rva; });
    fprintf(stderr, "[map] loaded %zu symbols from %s\n",
            g_map_syms.size(), mapPath.filename().string().c_str());
}

// Returns "name + 0xNNN" for a module-relative address, or empty if unknown.
static std::string symbolize_rva(uint32_t rva) {
    if (g_map_syms.empty()) return {};
    auto it = std::upper_bound(g_map_syms.begin(), g_map_syms.end(), rva,
                               [](uint32_t v, const MapSym& m) { return v < m.rva; });
    if (it == g_map_syms.begin()) return {};
    --it;
    char buf[320];
    snprintf(buf, sizeof(buf), "%s + 0x%X", it->name.c_str(), rva - it->rva);
    return buf;
}

// =============================================================================
// Main
// =============================================================================

static void print_stack(HANDLE thread, CONTEXT ctx, int max_frames);
static void print_peeks();

static LONG WINAPI crash_handler(EXCEPTION_POINTERS* ep) {
    fprintf(stderr, "\n[CRASH] Exception 0x%08lX at address 0x%p\n",
            ep->ExceptionRecord->ExceptionCode,
            ep->ExceptionRecord->ExceptionAddress);
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
        uintptr_t fault = (uintptr_t)ep->ExceptionRecord->ExceptionInformation[1];
        fprintf(stderr, "[CRASH] Access violation %s address 0x%p\n",
                ep->ExceptionRecord->ExceptionInformation[0] ? "writing" : "reading",
                (void*)fault);
        // Translate the fault back into an N64 address using the RDRAM base.
        if (g_rdram_base) {
            int64_t off = (int64_t)(fault - (uintptr_t)g_rdram_base);
            // MEM_B uses XOR 3 byte-swizzling, so undo it for the printed addr.
            uint32_t n64 = (uint32_t)(off + 0x80000000);
            uint32_t n64_b = (uint32_t)((off ^ 3) + 0x80000000);
            const char* tag = (off >= -0x10000 && off < 0x00900000)
                              ? "in RDRAM" : "out of RDRAM";
            fprintf(stderr, "[CRASH] rdram_base=%p offset=%+lld (%s)\n",
                    (void*)g_rdram_base, (long long)off, tag);
            fprintf(stderr, "[CRASH] -> N64 word addr ~0x%08X  byte addr ~0x%08X\n",
                    n64, n64_b);
        } else {
            fprintf(stderr, "[CRASH] rdram_base not set yet\n");
        }
    }
    // Print module + offset for the crash address
    HMODULE hMod = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                       (LPCSTR)ep->ExceptionRecord->ExceptionAddress, &hMod);
    if (hMod) {
        char modName[MAX_PATH];
        GetModuleFileNameA(hMod, modName, MAX_PATH);
        uintptr_t offset = (uintptr_t)ep->ExceptionRecord->ExceptionAddress - (uintptr_t)hMod;
        fprintf(stderr, "[CRASH] Module: %s + 0x%llX\n", modName, (unsigned long long)offset);
    }
    fprintf(stderr, "[CRASH] Stack trace (symbolized via .map):\n");
    print_stack(GetCurrentThread(), *ep->ContextRecord, 24);
    print_peeks();
    return EXCEPTION_EXECUTE_HANDLER;
}

// SWE1R_STACKDUMP=<seconds>: after that long, suspend every other thread and print its
// stack. For hangs: shows where each game thread is spinning or blocked.
static void stack_dump_thread(int seconds) {
    Sleep(seconds * 1000);
    DWORD self = GetCurrentThreadId(), pid = GetCurrentProcessId();
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    THREADENTRY32 te{ sizeof(te) };
    for (BOOL ok = Thread32First(snap, &te); ok; ok = Thread32Next(snap, &te)) {
        if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
        HANDLE th = OpenThread(THREAD_ALL_ACCESS, FALSE, te.th32ThreadID);
        if (!th) continue;
        SuspendThread(th);
        CONTEXT ctx{};
        ctx.ContextFlags = CONTEXT_FULL;
        if (GetThreadContext(th, &ctx)) {
            fprintf(stderr, "[STACK] thread %lu:\n", te.th32ThreadID);
            print_stack(th, ctx, 12);
        }
        ResumeThread(th);
        CloseHandle(th);
    }
    CloseHandle(snap);
    print_peeks();
}

// SWE1R_PEEK=0x80113690,0x...: print those RDRAM words at a stack dump or crash.
static void print_peeks() {
    if (const char* p = std::getenv("SWE1R_PEEK"); p && g_rdram_base) {
        for (char* end; *p; p = (*end ? end + 1 : end)) {
            uint32_t a = (uint32_t)strtoul(p, &end, 16);
            fprintf(stderr, "[PEEK] 0x%08X = 0x%08X\n", a, *(uint32_t*)(g_rdram_base + (a - 0x80000000u)));
            if (end == p) break;
        }
    }
    fflush(stderr);
}

// SWE1R_WATCH=<n64 addr>@<seconds>: after that delay, arm a hardware write watchpoint (DR0, 4
// bytes) on that RDRAM word in every thread. The first write traps into crash_handler, which
// prints the writer's stack. For finding who corrupts game memory.
static void watch_thread(uint32_t n64_addr, int seconds) {
    Sleep(seconds * 1000);
    if (!g_rdram_base) return;
    DWORD64 native = (DWORD64)(g_rdram_base + (n64_addr - 0x80000000u));
    fprintf(stderr, "[WATCH] armed on 0x%08X (native %p)\n", n64_addr, (void*)native);
    DWORD self = GetCurrentThreadId(), pid = GetCurrentProcessId();
    while (true) {  // re-arm periodically so threads created later are covered too
        HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        THREADENTRY32 te{ sizeof(te) };
        for (BOOL ok = Thread32First(snap, &te); ok; ok = Thread32Next(snap, &te)) {
            if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
            HANDLE th = OpenThread(THREAD_ALL_ACCESS, FALSE, te.th32ThreadID);
            if (!th) continue;
            SuspendThread(th);
            CONTEXT ctx{};
            ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
            if (GetThreadContext(th, &ctx) && ctx.Dr0 != native) {
                ctx.Dr0 = native;
                ctx.Dr7 = 0x000D0001; // L0, RW0=write, LEN0=4 bytes
                SetThreadContext(th, &ctx);
            }
            ResumeThread(th);
            CloseHandle(th);
        }
        CloseHandle(snap);
        Sleep(10);
    }
}

// Walk a thread's stack and symbolize each frame against the linker .map (which resolves
// the recompiled func_XXXX names) plus the PDB's C file:line.
static void print_stack(HANDLE thread, CONTEXT ctx, int max_frames) {
    static bool sym_init = SymInitialize(GetCurrentProcess(), NULL, TRUE);
    uintptr_t modBase = (uintptr_t)GetModuleHandle(NULL);
    STACKFRAME64 frame = {};
    frame.AddrPC.Offset = ctx.Rip;
    frame.AddrPC.Mode = AddrModeFlat;
    frame.AddrStack.Offset = ctx.Rsp;
    frame.AddrStack.Mode = AddrModeFlat;
    frame.AddrFrame.Offset = ctx.Rbp;
    frame.AddrFrame.Mode = AddrModeFlat;
    for (int i = 0; i < max_frames; i++) {
        if (!StackWalk64(IMAGE_FILE_MACHINE_AMD64, GetCurrentProcess(),
                         thread, &frame, &ctx, NULL,
                         SymFunctionTableAccess64, SymGetModuleBase64, NULL))
            break;
        uint64_t pc = frame.AddrPC.Offset;
        std::string name;
        if (pc >= modBase) name = symbolize_rva((uint32_t)(pc - modBase));
        IMAGEHLP_LINE64 line{ sizeof(IMAGEHLP_LINE64) };
        DWORD disp = 0;
        if (SymGetLineFromAddr64(GetCurrentProcess(), pc, &disp, &line))
            fprintf(stderr, "  [%d] %s   (%s:%lu)\n", i, name.c_str(), line.FileName, line.LineNumber);
        else if (!name.empty())
            fprintf(stderr, "  [%d] %s   (rva 0x%X)\n", i, name.c_str(),
                    (uint32_t)(pc - modBase));
        else
            fprintf(stderr, "  [%d] 0x%llX\n", i, (unsigned long long)pc);
    }
}
#endif // _WIN32

int main(int argc, char* argv[]) {
#ifdef _WIN32
    // Started from Explorer or a launcher (console window or none): keep the log, crash traces
    // included, in swe1racer.log next to the exe. Piped or redirected output is left alone.
    HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
    if (err == nullptr || err == INVALID_HANDLE_VALUE || GetFileType(err) == FILE_TYPE_CHAR) {
        char exe[MAX_PATH];
        DWORD n = GetModuleFileNameA(nullptr, exe, MAX_PATH);
        std::string log = std::string(exe, n);
        log = log.substr(0, log.find_last_of("\\/") + 1) + "swe1racer.log";
        freopen(log.c_str(), "w", stderr);
    }
#endif
    // Force unbuffered output so we see prints before crashes
    setvbuf(stdout, nullptr, _IONBF, 0);
    setvbuf(stderr, nullptr, _IONBF, 0);
#ifdef _WIN32
    load_map_symbols();
    SetUnhandledExceptionFilter(crash_handler);
    if (const char* s = std::getenv("SWE1R_STACKDUMP")) {
        std::thread(stack_dump_thread, std::atoi(s)).detach();
    }
    if (const char* w = std::getenv("SWE1R_WATCH")) {
        const char* at = strchr(w, '@');
        std::thread(watch_thread, (uint32_t)strtoul(w, nullptr, 16), at ? std::atoi(at + 1) : 0).detach();
    }
#endif

    fprintf(stderr, "[DEBUG] main() entered\n");

    printf("===========================================\n");
    printf("  Star Wars Episode I: Racer\n");
    printf("  N64 Static Recompilation v%d.%d.%d\n", 0, 2, 0);
    printf("  \"Now THIS is podracing!\"\n");
    printf("===========================================\n\n");

    // Register game entry
    recomp::GameEntry game_entry{};
    game_entry.rom_hash = SWE1R_ROM_HASH;
    game_entry.internal_name = "STAR WARS EP1 RACER";
    game_entry.display_name = "Star Wars Episode I: Racer";
    game_entry.game_id = u8"swe1racer";
    game_entry.mod_game_id = "swe1racer";
    game_entry.save_type = recomp::SaveType::Eep16k; // game addresses 256 EEPROM blocks (save at 0 and 0x400)
    game_entry.is_enabled = true;
    game_entry.entrypoint_address = (gpr)(int32_t)0x80000400; // Sign-extend for MEM macros
    game_entry.entrypoint = recomp_entrypoint;
    game_entry.on_init_callback = on_game_init;

    // Register overlay/section tables
    recomp::overlays::overlay_section_table_data_t sections_data{};
    sections_data.code_sections = section_table;
    sections_data.num_code_sections = num_sections;
    sections_data.total_num_sections = num_sections;

    recomp::overlays::overlays_by_index_t overlays_data{};
    overlays_data.table = nullptr;
    overlays_data.len = 0;

    recomp::overlays::register_overlays(sections_data, overlays_data);

    if (!recomp::register_game(game_entry)) {
        fprintf(stderr, "Failed to register game!\n");
        return 1;
    }

    printf("[SWE1R] Game registered: %zu sections, %zu functions in main section\n",
           num_sections, section_table[0].num_funcs);

    recomp::Configuration cfg{};
    cfg.project_version = { 0, 2, 0 };
    cfg.rsp_callbacks.get_rsp_microcode = get_rsp_microcode;
    cfg.events_callbacks.vi_callback = vi_callback;
    cfg.threads_callbacks.get_game_thread_name = get_game_thread_name;

    fe::GameInfo game;
    game.title = "Star Wars Episode I: Racer";
    game.game_id = u8"swe1racer";
    game.short_name = "swe1racer";
    game.rom_names = { "swe1racer.us.z64", "Star Wars Episode I - Racer (U) [!].z64", "baserom.z64" };
    game.players = 2;
    game.env_prefix = "SWE1R_";
    game.controller_bindings = fe::default_controller_bindings();
    // The D-pad also drives the stick: Racer steers and navigates menus with the stick.
    game.controller_bindings["StickUp"] = { "dpup" };
    game.controller_bindings["StickDown"] = { "dpdown" };
    game.controller_bindings["StickLeft"] = { "dpleft" };
    game.controller_bindings["StickRight"] = { "dpright" };
    game.netplay = true;
    // ponytail: the game's four OSThreads sit at fixed addresses; track osCreateThread if that changes.
    game.det_mask_words = { 0x000D7770, 0x000D7A20, 0x00149EF0, 0x0014B200 };
    game.det_ram_end = 0x00600000; // framebuffers (and RT64 write-backs) live above this

    printf("[SWE1R] Starting runtime...\n");
    printf("  \"It's working! IT'S WORKING!\" - Anakin Skywalker\n\n");
    return fe::run(game, cfg, argc, argv); // ends the process itself on a normal exit
}
