# Other builds: Linux arm64 and Android

Besides the game for the computer it's set up on, Racer can be built for two other kinds of
machine. The **Racer-Builds-Installer** on the release page does it (tick what you want), or
`./setup-builds.sh --targets linux-arm64,android` (Linux, macOS) or
`tools\setup-builds.ps1 -Targets linux-arm64,android` (Windows). Everything is built in Docker
from your own USA `.z64`, so Docker (Docker Desktop on Windows and macOS) must be installed and
running. The results land in `builds/`, the logs in `build-logs/`.

Each build contains your ROM (the game reads it at start), so it's yours to play, not to share.

Why only these two: the renderer, RT64, needs Vulkan, DirectX 12 or Metal with compute shaders.
The older consoles that the SkiFree and Link's Awakening ports build for have none of those, and
macOS can't be built in Docker (Apple's SDK is licensed for Macs only); build it on a Mac with
`setup.sh`.

## Linux arm64 — `builds/linux-arm64/racer-linux-arm64.tar.gz`

For a Raspberry Pi 5, ARM handhelds and ARM laptops, on Debian 12 / Raspberry Pi OS 12 or anything
newer, with a Vulkan driver. On an x86 computer it builds in an emulated container and takes a
few hours; on Apple silicon it's native and much quicker.

```
tar -xzf racer-linux-arm64.tar.gz
sudo apt install libsdl2-2.0-0 libgtk-3-0 mesa-vulkan-drivers
./racer/"Star Wars Episode I Racer.sh"
```

The log goes to `racer/swe1racer.log`; settings and saves sit next to it.

## Android — `builds/android/racer.apk`

For arm64 phones and handhelds with Vulkan (most from 2018 on). Install it like any APK from
outside the store: copy it over and open it (allowing installs from that app when asked), or
`adb install racer.apk`. Rebuilding signs with the same key (kept in `build-android/`), so a newer
build installs over the old one and keeps your saves.

- **It needs a controller**: a handheld's own buttons, or a Bluetooth or USB pad. There are no
  touch controls for driving yet; the menus work by touch.
- The log is `Android/data/net.sp00nz.racer/files/swe1racer.log` (a file manager or
  `adb shell cat /sdcard/Android/data/net.sp00nz.racer/files/swe1racer.log`).
- `RACER_ABI=x86_64` when running `scripts/build_android.sh` builds for the Android emulator
  instead.

## What's been tested

- Android: the x86_64 build in the Android emulator (Vulkan through the host GPU) boots to the
  launcher, the title screen and the game's intro; the arm64 build builds but hasn't been on a
  phone yet.
- Linux arm64: in an emulated arm64 Debian 13 container (software Vulkan), the launcher comes up
  and the game starts; not yet on a Raspberry Pi. Debian 12's own software Vulkan (lavapipe, Mesa
  22.3) crashes while compiling RT64's shaders, on x86 too; Mesa 24 and newer is fine. The Pi's
  GPU uses a different driver (v3dv), so that crash may not apply there.
