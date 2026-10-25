#!/bin/bash
# Turns baserom.z64 into C (RecompiledFuncs/, rsp/aspMain.cpp) for setup-builds: the same as
# setup.sh's steps 3 to 5, in the docker/linux.Dockerfile image. Its recompiler goes in
# build-tools/, apart from the one a native setup builds in deps/N64Recomp/build.
set -e
cd "$(dirname "$0")/.."
for t in N64Recomp N64ModernRuntime rt64; do
  [ -d "deps/$t/.git" ] || git clone -q --recurse-submodules --branch main "https://github.com/sp00nznet/$t" "deps/$t"
done
T=build-tools/N64Recomp
if [ ! -x $T/N64Recomp ] || [ ! -x $T/RSPRecomp ]; then
  cmake -S deps/N64Recomp -B $T -G Ninja -DCMAKE_BUILD_TYPE=Release
  cmake --build $T --target N64RecompCLI RSPRecomp
fi
# Redone whenever the recompiler's inputs change. setup.sh keeps the same stamp, and
# tools/setup.ps1 an upper-case one: either counts, so a native build and these share the output.
inputs=$(python3 -c 'import hashlib, sys; print("".join(hashlib.sha256(open(f, "rb").read()).hexdigest() for f in sys.argv[1:]))' symbols.toml recomp.toml rsp/aspMain.toml)
stamp=RecompiledFuncs/inputs.txt
if [ -f "$stamp" ] && [ "$(tr A-F a-f < "$stamp")" = "$inputs" ] && [ -f rsp/aspMain.cpp ]; then
  echo "already recompiled"; exit 0
fi
rm -rf RecompiledFuncs; mkdir RecompiledFuncs
$T/N64Recomp recomp.toml
python3 tools/fix_fallthroughs.py
python3 tools/post_recomp_patches.py
$T/RSPRecomp rsp/aspMain.toml
printf '%s' "$inputs" > "$stamp"
