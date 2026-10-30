#!/bin/bash
# Star Wars Episode I: Racer recomp setup for Linux and macOS: from a plain download to a launcher,
# using your own ROM. The same steps as tools/setup.ps1 (Windows).
#
#   ./setup.sh                    asks before installing anything
#   ./setup.sh --yes --game DIR   no questions (recomp-launcher uses this)
#   ./setup.sh --targets pc,android,linux-arm64   also build for other machines, in Docker
#
# Targets: pc (this computer, the default) and the builds in scripts/targets.tsv, which
# setup-builds.sh makes after this computer's. Only the picked ones' toolchains are downloaded.
#
# It skips the steps already done (so a rerun after a failure resumes) and logs everything to
# logs/setup.log. The ROM stays on this machine: it's copied into this folder as baserom.z64
# (gitignored) and recompiled here. Nothing from the game is downloaded.
set -e
cd "$(dirname "$0")"
ROOT=$PWD
YES=0; GAME=""; TARGETS=pc
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --game|--game-dir) GAME=$2; shift ;;
    --targets) TARGETS=${2:-pc}; shift ;;
    *) echo "usage: ./setup.sh [--yes] [--game DIR] [--targets pc,android,linux-arm64]" >&2; exit 2 ;;
  esac
  shift
done
OTHERS=$(echo ",$TARGETS," | sed 's/,pc,/,/g; s/^,*//; s/,*$//')
builds() {
  args=(--targets "$OTHERS"); [ $YES = 1 ] && args+=(--yes); [ -n "$GAME" ] && args+=(--game "$GAME")
  exec bash "$ROOT/setup-builds.sh" "${args[@]}"
}
# Only other machines: that's setup-builds.sh's job alone.
case ",$TARGETS," in *,pc,*) ;; *) builds ;; esac
mkdir -p logs deps
LOG=$ROOT/logs/setup.log
echo "Racer recomp setup, $(date)" > "$LOG"

TITLE="Star Wars Episode I Racer"
STEPS=7
STEP=0

# "[n/7] what": recomp-launcher's progress bar reads these.
step() { STEP=$((STEP + 1)); echo "[$STEP/$STEPS] $*"; echo "[$STEP/$STEPS] $*" >> "$LOG"; }
fail() {
  echo ""; echo "Setup stopped: $*" >&2; echo "Details are in $LOG" >&2
  echo "Setup stopped: $*" >> "$LOG"; exit 1
}
# Runs a command with its output in the log; stops with $1 if it fails.
run() { why=$1; shift; echo "> $*" >> "$LOG"; "$@" >> "$LOG" 2>&1 || fail "$why"; }
ask() { [ "$YES" = 1 ] && return 0; read -r -p "$1 [Y/n] " r; case "$r" in [nN]*) return 1 ;; esac; return 0; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------------------------
step "Checking the tools it needs"
MAC=0; [ "$(uname)" = Darwin ] && MAC=1
if [ $MAC = 1 ]; then
  # RT64 compiles its Metal shaders with Xcode's metal compiler (the Command Line Tools lack it).
  xcrun -sdk macosx metal --version >/dev/null 2>&1 ||
    fail "Xcode is needed (for its Metal shader compiler). Install Xcode from the App Store, open it once, run 'xcodebuild -downloadComponent MetalToolchain' if it asks for the Metal toolchain, then run Setup again."
  missing=""
  for t in cmake ninja python3; do have $t || missing="$missing $t"; done
  [ -e "$(brew --prefix 2>/dev/null)/lib/cmake/SDL2/SDL2Config.cmake" ] || missing="$missing sdl2"
  if [ -n "$missing" ]; then
    have brew || fail "these are missing:$missing. Install Homebrew (https://brew.sh), then run Setup again."
    ask "These are needed to build the game and aren't installed:$missing. Install them with Homebrew?" || fail "install$missing, then run Setup again."
    run "installing$missing with Homebrew failed" brew install $missing
  fi
else
  missing_cmd=""
  for t in git cmake ninja clang++ python3 pkg-config; do have $t || missing_cmd="$missing_cmd $t"; done
  missing_lib=""
  for p in sdl2 gtk+-3.0 x11 xrandr; do have pkg-config && pkg-config --exists $p || missing_lib="$missing_lib $p"; done
  if [ -n "$missing_cmd$missing_lib" ]; then
    if have apt-get; then pm="apt-get install -y"; pkgs="git cmake ninja-build clang python3 pkg-config libsdl2-dev libgtk-3-dev libx11-dev libxrandr-dev"
    elif have dnf; then pm="dnf install -y"; pkgs="git cmake ninja-build clang python3 pkgconf-pkg-config SDL2-devel gtk3-devel libX11-devel libXrandr-devel"
    elif have pacman; then pm="pacman -S --needed --noconfirm"; pkgs="git cmake ninja clang python pkgconf sdl2 gtk3 libx11 libxrandr"
    else fail "missing:$missing_cmd$missing_lib. Install them (the SDL2, GTK 3, X11 and Xrandr development packages, clang, cmake, ninja), then run Setup again."
    fi
    ask "Some build tools and libraries are missing:$missing_cmd$missing_lib. Install them with 'sudo $pm' (asks for your password)?" ||
      fail "install them with: sudo $pm $pkgs"
    [ "$pm" = "apt-get install -y" ] && run "updating the package list failed" sudo apt-get update
    run "installing the build tools failed" sudo $pm $pkgs
  fi
fi

# ---------------------------------------------------------------------------------------------
step "Finding your ROM"
match=$(python3 tools/find_rom.py "$ROOT" ${GAME:+"$GAME"})
[ -n "$match" ] || fail "No Racer ROM found. Put your USA .z64 of Star Wars Episode I: Racer in this folder (or pass --game <folder>), then run Setup again. Byte-swapped .v64/.n64 dumps need converting to .z64 first."
[ "$match" = "$ROOT/baserom.z64" ] || cp "$match" "$ROOT/baserom.z64"
echo "  $match"

# ---------------------------------------------------------------------------------------------
step "Getting the recompiler, runtime and renderer"
# sp00nznet's forks, which carry the fixes Racer needs (README, Building).
for t in N64Recomp N64ModernRuntime rt64; do
  [ -d "deps/$t/.git" ] && continue
  run "downloading $t failed (no internet, or see the log)" git clone --recurse-submodules --branch main "https://github.com/sp00nznet/$t" "deps/$t"
done

# ---------------------------------------------------------------------------------------------
step "Building the recompiler"
RECOMP=$ROOT/deps/N64Recomp/build/N64Recomp
RSPRECOMP=$ROOT/deps/N64Recomp/build/RSPRecomp
if [ ! -x "$RECOMP" ] || [ ! -x "$RSPRECOMP" ]; then
  run "configuring N64Recomp failed" cmake -S deps/N64Recomp -B deps/N64Recomp/build -G Ninja -DCMAKE_BUILD_TYPE=Release
  run "building N64Recomp failed" cmake --build deps/N64Recomp/build --target N64RecompCLI RSPRecomp
fi

# ---------------------------------------------------------------------------------------------
step "Recompiling your game (a minute or two)"
# Redone whenever the recompiler's inputs change (an update to symbols.toml or recomp.toml).
inputs=$(python3 -c 'import hashlib, sys; print("".join(hashlib.sha256(open(f, "rb").read()).hexdigest() for f in sys.argv[1:]))' symbols.toml recomp.toml rsp/aspMain.toml)
stamp=RecompiledFuncs/inputs.txt
if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$inputs" ] || [ ! -f rsp/aspMain.cpp ]; then
  rm -rf RecompiledFuncs; mkdir RecompiledFuncs
  run "recompiling failed" "$RECOMP" recomp.toml
  run "patching the recompiled code failed" python3 tools/fix_fallthroughs.py
  run "patching the recompiled code failed" python3 tools/post_recomp_patches.py
  # The audio microcode (libultra's aspMain) runs as recompiled C++ too.
  run "recompiling the audio microcode failed" "$RSPRECOMP" rsp/aspMain.toml
  printf '%s' "$inputs" > "$stamp"
fi

# ---------------------------------------------------------------------------------------------
step "Building (the first build takes 20 to 40 minutes)"
compilers=""; [ $MAC = 0 ] && compilers="-DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++"
run "configuring the game failed" cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo $compilers
run "building the game failed" cmake --build build --target SWE1Racer

# ---------------------------------------------------------------------------------------------
step "Making the launcher"
# A .command opens from Finder; recomp-launcher runs either with /bin/sh.
ext=sh; [ $MAC = 1 ] && ext=command
launcher="$TITLE (recomp).$ext"
cat > "$launcher" <<'EOF'
#!/bin/sh
cd "$(dirname "$0")"
exec build/SWE1Racer "$@" 2> build/swe1racer.log
EOF
chmod +x "$launcher"
echo "  $launcher"
echo ""
echo "Done. Run the launcher above to play."
[ -z "$OTHERS" ] || { echo ""; builds; }
