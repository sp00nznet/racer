#!/bin/bash
# The Android build (arm64 phones and handhelds with Vulkan), in the docker/android.Dockerfile
# image. Puts SDL's Android project template together with android/ (our manifest and app
# module) and your ROM, and runs Gradle. Leaves builds/android/racer.apk.
# RACER_ABI=x86_64 builds for the Android emulator instead.
set -e
cd "$(dirname "$0")/.."
export RACER_ROOT=$PWD
: "${ANDROID_HOME:?set ANDROID_HOME to the Android SDK}"
: "${SDL2_SRC:?set SDL2_SRC to an SDL2 2.32.x source tree}"
B=$RACER_ROOT/build-android
mkdir -p $B

# RT64 runs file_to_c while it builds, so it needs one for this machine, not the phone.
export HOST_FILE_TO_C=$B/file_to_c
[ -x $HOST_FILE_TO_C ] || c++ -O2 -std=c++17 -o $HOST_FILE_TO_C deps/rt64/src/tools/file_to_c/file_to_c.cpp

P=$B/project
rm -rf $P && cp -r "$SDL2_SRC/android-project" $P
rm -rf $P/app/jni
cp -r android/app/. $P/app/
mkdir -p $P/app/src/main/assets && cp baserom.z64 $P/app/src/main/assets/
echo "sdk.dir=$ANDROID_HOME" > $P/local.properties
# SDL's template pins Gradle 8.1.1, which can't run on the image's Java 21: Gradle 8.9 and AGP 8.7.
sed -i 's|gradle-8.1.1-bin.zip|gradle-8.9-bin.zip|' $P/gradle/wrapper/gradle-wrapper.properties
sed -i "s|com.android.tools.build:gradle:8.1.1|com.android.tools.build:gradle:8.7.3|" $P/build.gradle
# The signing key lives here (ANDROID_USER_HOME), not in the container: the same key every build,
# so a new APK installs over the last one and keeps your saves.
GRADLE_USER_HOME=$B/.gradle ANDROID_USER_HOME=$B/android-home bash $P/gradlew -p $P assembleRelease --console=plain

mkdir -p builds/android
cp $P/app/build/outputs/apk/release/app-release.apk builds/android/racer.apk
ls -la builds/android/racer.apk
