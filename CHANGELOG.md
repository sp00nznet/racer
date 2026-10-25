# Changelog

## v0.3.0 (2026-10-25)

Builds for other machines. The release page has a second set of installers, Racer-Builds-Installer
for Windows, Linux and macOS: tick Linux arm64, Android or both, and it builds them from your own
ROM in Docker. The first set, which builds and plays the game on the computer itself, is unchanged.

- Linux arm64: for a Raspberry Pi 5 and other arm64 Linux with Vulkan (Debian 12 or newer).
- Android: an `.apk` for arm64 phones and handhelds with Vulkan; needs a controller for driving.
- Fixed: on the very first run the launcher asked for the ROM again after finding it.
- How to install each: docs/other-builds.md.

Known issues: neither build has run on its real hardware yet (Android was tried in the emulator
up to the game's intro; Linux arm64 only in an emulated container, where it runs but too slowly
to show the game); no touch controls on Android.

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
