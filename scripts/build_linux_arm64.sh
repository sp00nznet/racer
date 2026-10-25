#!/bin/bash
# The Linux arm64 build (Raspberry Pi 5, ARM handhelds and laptops with a Vulkan driver), in the
# docker/linux.Dockerfile image run as linux/arm64. Leaves builds/linux-arm64/racer-linux-arm64.tar.gz.
set -e
cd "$(dirname "$0")/.."
B=build-linux-arm64
cmake -S . -B $B -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DN64_MODERN_RUNTIME_DIR="$PWD/deps/N64ModernRuntime" -DRT64_DIR="$PWD/deps/rt64"
cmake --build $B --target SWE1Racer

# The game, your ROM (it looks next to itself for baserom.z64) and a launcher, in one folder.
P=$B/racer
rm -rf $P && mkdir -p $P
cp $B/SWE1Racer $P/ && strip $P/SWE1Racer
cp baserom.z64 $P/
cat > "$P/Star Wars Episode I Racer.sh" <<'EOF'
#!/bin/sh
# Needs SDL2, GTK 3 and a Vulkan driver: sudo apt install libsdl2-2.0-0 libgtk-3-0 mesa-vulkan-drivers
cd "$(dirname "$0")"
exec ./SWE1Racer "$@" 2> swe1racer.log
EOF
chmod +x "$P/Star Wars Episode I Racer.sh"
mkdir -p builds/linux-arm64
tar -C $B -czf builds/linux-arm64/racer-linux-arm64.tar.gz racer
file $P/SWE1Racer
