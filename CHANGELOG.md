# Changelog

## v0.2.0 (2026-10-25)

Linux and macOS. The release page now has an installer for each of Windows, Linux and macOS; on
Linux and macOS it runs the new `setup.sh` (or run it yourself), which builds the game from your own
ROM the same way `Setup.cmd` does on Windows.

- Linux: Vulkan renderer, SDL2 and GTK 3 from your package manager (apt, dnf or pacman).
- macOS (Apple Silicon): Metal renderer; needs Xcode, and SDL2 from Homebrew.
- The launcher and in-game menu draw on Vulkan and Metal as well as DirectX 12.
- Fixed: a crash when quitting, from the game's threads outliving the runtime (seen on Linux).

Known issues: the macOS build is compile-checked only (no Mac to play it on yet); the Linux build was
played on a software GPU, not real hardware; the crash-trace tools are Windows only. Netplay between
different operating systems is untested.

## v0.1.0 (2026-10-24)

First release. Install with the recomp-launcher installer on the release page (or `Setup.cmd`): it
takes your own USA `.z64`, recompiles it on your machine and builds the game. Nothing from the game
is downloaded or shipped.

- Plays from boot through menus, tournament and free play into full races.
- RT64 renderer (DirectX 12): high resolution, MSAA, widescreen (experimental), texture packs, fullscreen (F11).
- Sound: the game's audio microcode recompiled, with a volume setting.
- Launcher and in-game menu (Esc or the controller's Back button): controls, graphics, sound, netplay and cheats.
- Controllers with drop-in/drop-out for 2 players, keyboard, rebinding.
- 2-player netplay over LAN or internet (deterministic lockstep).
- GameShark cheats from a Project64 `.cht` list (Settings > Cheats).
- Fixed: a mid-race freeze when the sound queue backed up.

Known issues: netplay is untested across two physical machines; widescreen leaves the game's 4:3
blur overlay; Windows only.
