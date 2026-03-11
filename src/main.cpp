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

#include <SDL.h>
#include <SDL_syswm.h>

#include "recomp.h"
#include "librecomp/game.hpp"
#include "librecomp/overlays.hpp"
#include "librecomp/rsp.hpp"
#include "ultramodern/ultramodern.hpp"
#include "ultramodern/renderer_context.hpp"
#include "ultramodern/error_handling.hpp"
#include "ultramodern/events.hpp"
#include "ultramodern/input.hpp"
#include "ultramodern/threads.hpp"

// =============================================================================
// External declarations
// =============================================================================

// From section_table.cpp
extern SectionTableEntry section_table[];
extern const size_t num_sections;

// From rt64_render_context.cpp
extern std::unique_ptr<ultramodern::renderer::RendererContext> create_swe1r_render_context(
    uint8_t* rdram, ultramodern::renderer::WindowHandle window_handle, bool developer_mode);

// The recompiled entrypoint function
extern "C" void recomp_entrypoint(uint8_t* rdram, recomp_context* ctx);

// From audio.cpp
extern void swe1r_queue_samples(int16_t* samples, size_t num_samples);
extern size_t swe1r_get_frames_remaining();
extern void swe1r_set_frequency(uint32_t freq);

// =============================================================================
// ROM Hash: Star Wars Episode I: Racer (US)
// CRC1: 0x72F70398  CRC2: 0x6556A98B
// =============================================================================
constexpr uint64_t SWE1R_ROM_HASH = (uint64_t(0x72F70398) << 32) | uint64_t(0x6556A98B);

// =============================================================================
// Global state
// =============================================================================
static SDL_Window* g_window = nullptr;

// =============================================================================
// RSP Callbacks
// =============================================================================

// SWE1R RSP microcode identification
// The game uses standard Fast3D-derived microcode for graphics
// and ABI microcode for audio
RspUcodeFunc* get_rsp_microcode(const OSTask* task) {
    // TODO: Identify SWE1R's specific microcode and return handlers
    // For now, return nullptr (will cause RSP tasks to fail gracefully)
    return nullptr;
}

// =============================================================================
// Renderer Callbacks
// =============================================================================

std::unique_ptr<ultramodern::renderer::RendererContext> create_render_context_callback(
    uint8_t* rdram, ultramodern::renderer::WindowHandle window_handle, bool developer_mode) {
    return create_swe1r_render_context(rdram, window_handle, developer_mode);
}

// =============================================================================
// GFX Callbacks (window management)
// =============================================================================

ultramodern::gfx_callbacks_t::gfx_data_t create_gfx() {
    SDL_SetHint(SDL_HINT_WINDOWS_DPI_AWARENESS, "permonitorv2");
    SDL_SetHint(SDL_HINT_GAMECONTROLLER_USE_BUTTON_LABELS, "0");

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | SDL_INIT_AUDIO) < 0) {
        fprintf(stderr, "Failed to initialize SDL2: %s\n", SDL_GetError());
        std::exit(1);
    }

    printf("[SWE1R] SDL initialized: %s\n", SDL_GetCurrentVideoDriver());
    return nullptr;
}

ultramodern::renderer::WindowHandle create_window(ultramodern::gfx_callbacks_t::gfx_data_t) {
    g_window = SDL_CreateWindow(
        "Star Wars Episode I: Racer",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        1280, 960,
        SDL_WINDOW_RESIZABLE
    );

    if (!g_window) {
        fprintf(stderr, "Failed to create window: %s\n", SDL_GetError());
        std::exit(1);
    }

    printf("[SWE1R] Window created (1280x960)\n");

    // Return native window handle
    SDL_SysWMinfo wminfo;
    SDL_VERSION(&wminfo.version);
    SDL_GetWindowWMInfo(g_window, &wminfo);

    ultramodern::renderer::WindowHandle handle{};
    handle.window = wminfo.info.win.window;
    handle.thread_id = GetCurrentThreadId();
    return handle;
}

void update_gfx(ultramodern::gfx_callbacks_t::gfx_data_t) {
    // Process SDL events
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        switch (event.type) {
            case SDL_QUIT:
                ultramodern::quit();
                break;
            case SDL_KEYDOWN:
                if (event.key.keysym.sym == SDLK_ESCAPE) {
                    ultramodern::quit();
                }
                break;
        }
    }
}

// =============================================================================
// Input Callbacks (stub)
// =============================================================================

void poll_input() {
    // SDL event polling is done in update_gfx
}

bool get_input(int controller_num, uint16_t* buttons, float* x, float* y) {
    if (controller_num != 0) return false;

    *buttons = 0;
    *x = 0.0f;
    *y = 0.0f;

    // Basic keyboard input
    const uint8_t* keys = SDL_GetKeyboardState(nullptr);

    // N64 button mappings
    if (keys[SDL_SCANCODE_RETURN]) *buttons |= 0x8000; // A
    if (keys[SDL_SCANCODE_LSHIFT]) *buttons |= 0x4000; // B
    if (keys[SDL_SCANCODE_Z])      *buttons |= 0x2000; // Z
    if (keys[SDL_SCANCODE_SPACE])  *buttons |= 0x1000; // Start
    if (keys[SDL_SCANCODE_UP])     *buttons |= 0x0800; // D-Up
    if (keys[SDL_SCANCODE_DOWN])   *buttons |= 0x0400; // D-Down
    if (keys[SDL_SCANCODE_LEFT])   *buttons |= 0x0200; // D-Left
    if (keys[SDL_SCANCODE_RIGHT])  *buttons |= 0x0100; // D-Right

    // Analog stick via WASD
    if (keys[SDL_SCANCODE_W]) *y += 1.0f;
    if (keys[SDL_SCANCODE_S]) *y -= 1.0f;
    if (keys[SDL_SCANCODE_A]) *x -= 1.0f;
    if (keys[SDL_SCANCODE_D]) *x += 1.0f;

    return true;
}

void set_rumble(int controller_num, bool rumble) {
    // TODO: SDL haptic feedback
}

ultramodern::input::connected_device_info_t get_connected_device_info(int controller_num) {
    if (controller_num == 0) {
        return { ultramodern::input::Device::Controller, ultramodern::input::Pak::None };
    }
    return { ultramodern::input::Device::None, ultramodern::input::Pak::None };
}

// =============================================================================
// Event Callbacks
// =============================================================================

void vi_callback() {
    // Called every VI interrupt
}

void gfx_init_callback() {
    printf("[SWE1R] Graphics initialized\n");
}

// =============================================================================
// Error Handling
// =============================================================================

void error_message_box(const char* msg) {
    fprintf(stderr, "[SWE1R ERROR] %s\n", msg);
    if (g_window) {
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "SWE1R Error", msg, g_window);
    }
}

// =============================================================================
// Thread Naming
// =============================================================================

std::string get_game_thread_name(const OSThread* t) {
    return "SWE1R-Thread";
}

// =============================================================================
// Main
// =============================================================================

int main(int argc, char* argv[]) {
    printf("===========================================\n");
    printf("  Star Wars Episode I: Racer\n");
    printf("  N64 Static Recompilation v%d.%d.%d\n", 0, 1, 0);
    printf("  \"Now THIS is podracing!\"\n");
    printf("===========================================\n\n");

    // Register game entry
    recomp::GameEntry game_entry{};
    game_entry.rom_hash = SWE1R_ROM_HASH;
    game_entry.internal_name = "STAR WARS EP1 RACER";
    game_entry.game_id = u8"swe1racer";
    game_entry.mod_game_id = "swe1racer";
    game_entry.save_type = recomp::SaveType::Eep4k;
    game_entry.is_enabled = true;
    game_entry.entrypoint_address = 0x80000400;
    game_entry.entrypoint = recomp_entrypoint;

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

    // Set up config path
    recomp::register_config_path(std::filesystem::current_path());

    // Build the configuration
    recomp::Configuration cfg{};
    cfg.project_version = { 0, 1, 0, "-alpha" };

    // RSP callbacks
    recomp::rsp::callbacks_t rsp_callbacks{};
    rsp_callbacks.get_rsp_microcode = get_rsp_microcode;
    cfg.rsp_callbacks = rsp_callbacks;

    // Renderer callbacks
    ultramodern::renderer::callbacks_t renderer_callbacks{};
    renderer_callbacks.create_render_context = create_render_context_callback;
    cfg.renderer_callbacks = renderer_callbacks;

    // Audio callbacks
    ultramodern::audio_callbacks_t audio_callbacks{};
    audio_callbacks.queue_samples = swe1r_queue_samples;
    audio_callbacks.get_frames_remaining = swe1r_get_frames_remaining;
    audio_callbacks.set_frequency = swe1r_set_frequency;
    cfg.audio_callbacks = audio_callbacks;

    // Input callbacks
    ultramodern::input::callbacks_t input_callbacks{};
    input_callbacks.poll_input = poll_input;
    input_callbacks.get_input = get_input;
    input_callbacks.set_rumble = set_rumble;
    input_callbacks.get_connected_device_info = get_connected_device_info;
    cfg.input_callbacks = input_callbacks;

    // GFX callbacks (window management)
    ultramodern::gfx_callbacks_t gfx_callbacks{};
    gfx_callbacks.create_gfx = create_gfx;
    gfx_callbacks.create_window = create_window;
    gfx_callbacks.update_gfx = update_gfx;
    cfg.gfx_callbacks = gfx_callbacks;

    // Events callbacks
    ultramodern::events::callbacks_t events_callbacks{};
    events_callbacks.vi_callback = vi_callback;
    events_callbacks.gfx_init_callback = gfx_init_callback;
    cfg.events_callbacks = events_callbacks;

    // Error handling
    ultramodern::error_handling::callbacks_t error_callbacks{};
    error_callbacks.message_box = error_message_box;
    cfg.error_handling_callbacks = error_callbacks;

    // Threads
    ultramodern::threads::callbacks_t threads_callbacks{};
    threads_callbacks.get_game_thread_name = get_game_thread_name;
    cfg.threads_callbacks = threads_callbacks;

    printf("[SWE1R] Starting runtime...\n");
    printf("  \"It's working! IT'S WORKING!\" - Anakin Skywalker\n\n");

    // Load ROM and start game
    std::u8string game_id = u8"swe1racer";
    recomp::start_game(game_id);

    // This blocks until the game exits
    recomp::start(cfg);

    // Cleanup
    if (g_window) {
        SDL_DestroyWindow(g_window);
    }
    SDL_Quit();

    printf("\n[SWE1R] Shutdown complete.\n");
    return 0;
}
