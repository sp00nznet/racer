#!/bin/bash
# Builds Star Wars Episode I: Racer from your ROM for the other machines in scripts/targets.tsv
# (Linux arm64, Android), in Docker (Linux and macOS; Windows runs tools/setup-builds.ps1, which
# does the same). Every toolchain runs in a container: nothing but Docker is installed here.
#
#   ./setup-builds.sh [--yes] [--game <folder with your ROM>] [--targets linux-arm64,android]
#
# Each step prints "[n/N] ...", and a failure ends with "Setup stopped: ...", for recomp-launcher
# (launcher-builds/launcher.json). A build that fails doesn't stop the others; its log is in
# build-logs/. The results land in builds/. Finished work is skipped on a rerun.
# No "set -u": macOS bash 3.2 treats an empty array as unset under it.
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
YES=0 GAME="" ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --game|--game-dir) GAME="$2"; shift ;;
    --targets) ONLY=",$2,"; shift ;;
    *) echo "usage: ./setup-builds.sh [--yes] [--game DIR] [--targets a,b]" >&2; exit 2 ;;
  esac
  shift
done
mkdir -p build-logs builds
exec > >(tee build-logs/setup.log) 2>&1

TARGETS=()
while IFS= read -r line; do
  case "$line" in \#*|"") continue ;; esac
  t="${line%%$'\t'*}"
  if [ -z "$ONLY" ] || [[ "$ONLY" == *",$t,"* ]]; then TARGETS+=("$line"); fi
done < scripts/targets.tsv
N=$((3 + ${#TARGETS[@]}))

step() { echo; echo "[$1/$N] $2"; }
fail() { echo; echo "Setup stopped: $1"; echo "Details are in $ROOT/build-logs/setup.log"; exit 1; }
# Docker Desktop (macOS) maps file owners itself; on Linux run as you, so what the
# containers write is yours.
USER_ARGS=()
[ "$(uname)" = Linux ] && USER_ARGS=(-u "$(id -u):$(id -g)" -e HOME=/tmp)
# image <tag> <platform, or "" for this machine's> <dockerfile>: built on first use (Docker
# caches it after that).
image() {
  docker image inspect "$1" >/dev/null 2>&1 && return
  docker build -t "$1" ${2:+--platform "$2"} -f "docker/$3.Dockerfile" docker
}

step 1 "Checking Docker"
command -v docker >/dev/null || fail "Docker isn't installed. Install it (https://docs.docker.com/get-docker/), start it, and run this again."
docker info >/dev/null 2>&1 || fail "Docker isn't running. Start it and run this again."
[ ${#TARGETS[@]} -gt 0 ] || fail "none of '$ONLY' is in scripts/targets.tsv."
echo "  Docker $(docker version --format '{{.Server.Version}}')"

step 2 "Finding your ROM"
image racer-linux "" linux > build-logs/image-linux.log 2>&1 || fail "building the Linux toolchain image failed (build-logs/image-linux.log)."
if [ -n "$GAME" ]; then
  [ -e "$GAME" ] || fail "there's nothing at '$GAME'."
  [ -f "$GAME" ] && GAME="$(dirname "$GAME")"
  GAMEDIR=(-v "$(cd "$GAME" && pwd):/game:ro")
else
  GAMEDIR=()
fi
found="$(docker run --rm "${USER_ARGS[@]}" -v "$ROOT:/src" "${GAMEDIR[@]}" -w /src racer-linux python3 tools/find_rom.py /src /game)"
[ -n "$found" ] || fail "No Racer ROM found. Choose the folder with your USA .z64 of Star Wars Episode I: Racer (byte-swapped .v64/.n64 dumps need converting to .z64 first)."
[ "$found" = /src/baserom.z64 ] || docker run --rm "${USER_ARGS[@]}" -v "$ROOT:/src" "${GAMEDIR[@]}" racer-linux cp "$found" /src/baserom.z64
echo "  ${found#/game/}"

step 3 "Turning your ROM into C (a few minutes; the first run also downloads the toolkits)"
docker run --rm "${USER_ARGS[@]}" -v "$ROOT:/src" -w /src racer-linux bash scripts/recompile.sh > build-logs/recompile.log 2>&1 ||
  fail "recompiling failed (build-logs/recompile.log)."

n=3; ok=(); bad=()
for line in "${TARGETS[@]}"; do
  IFS=$'\t' read -r t platform tag dockerfile script out state <<<"$line"
  n=$((n + 1))
  step $n "$t: building (30 minutes to a few hours; the first run also downloads its toolchain)"
  if ! image "$tag" "$platform" "$dockerfile" > "build-logs/$t.log" 2>&1; then
    echo "  Building the $t toolchain image failed."; bad+=("$t"); continue
  fi
  if docker run --rm "${USER_ARGS[@]}" --platform "$platform" -v "$ROOT:/src" -w /src "$tag" bash "$script" >> "build-logs/$t.log" 2>&1 && [ -f "$out" ]; then
    ok+=("$t"); echo "  Built: $out ($state)."
  else
    bad+=("$t"); echo "  Failed. The last lines of build-logs/$t.log:"; tail -n 5 "build-logs/$t.log" | sed 's/^/    /'
  fi
done

[ ${#ok[@]} -gt 0 ] || fail "nothing built. The logs in build-logs/ say why."
launcher="Other builds (recomp).sh"
[ "$(uname)" = Darwin ] && launcher="Other builds (recomp).command"
printf '#!/bin/sh\n# Opens the folder with the builds.\ncd "$(dirname "$0")/builds" && { open . 2>/dev/null || xdg-open .; }\n' > "$launcher"
chmod +x "$launcher"
echo
echo "Done: ${#ok[@]} of ${#TARGETS[@]} built${bad:+ (failed: ${bad[*]})}. They're in builds/; docs/other-builds.md says how to install each."
