#!/usr/bin/env bash
set -e

export SOURCE_DATE_EPOCH=0
export ZERO_AR_DATE=1

SUDO=""

# Use sudo if not root
if [[ ! $(id -u) -eq 0 ]]; then
  if [[ -z $(which sudo) ]]; then
    echo "Please install sudo or run as root"
    exit 1
  fi
  SUDO="sudo"
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
cd $DIR

RAYLIB_PLATFORM="PLATFORM_DESKTOP"

ARCHNAME=$(uname -m)
if [ -f /TICI ]; then
  ARCHNAME="larch64"
  RAYLIB_PLATFORM="PLATFORM_COMMA"
elif [[ "$OSTYPE" == "linux"* ]]; then
  if [[ -n "${CI:-}" ]]; then
    # CI: use offscreen EGL surfaceless platform (no X11/Xvfb needed)
    RAYLIB_PLATFORM="PLATFORM_OFFSCREEN"
    $SUDO apt-get install -y --no-install-recommends \
      libegl-dev \
      libgl-dev
  else
    # Desktop: use GLFW with X11
    $SUDO apt install \
      libxcursor-dev \
      libxi-dev \
      libxinerama-dev \
      libxrandr-dev
  fi
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
  ARCHNAME="Darwin"
fi

INSTALL_DIR="$DIR/$ARCHNAME"
rm -rf $INSTALL_DIR
mkdir -p $INSTALL_DIR

INSTALL_H_DIR="$DIR/include"
rm -rf $INSTALL_H_DIR
mkdir -p $INSTALL_H_DIR

if [ ! -d raylib_repo ]; then
  git clone -b master --no-tags https://github.com/commaai/raylib.git raylib_repo
fi

cd raylib_repo

COMMIT=${1:-d9d7cc1353ec0f73c97e84ddf0973983d1ee25e2}
git fetch origin $COMMIT
git reset --hard $COMMIT
git clean -xdff .

cd src

make -j$(nproc) PLATFORM=$RAYLIB_PLATFORM RAYLIB_RELEASE_PATH=$INSTALL_DIR
cp raylib.h raymath.h rlgl.h $INSTALL_H_DIR/
echo "raylib development files installed/updated in $INSTALL_H_DIR"

# this commit needs to be in line with raylib
set -x
RAYGUI_COMMIT="76b36b597edb70ffaf96f046076adc20d67e7827"
curl -fsSLo $INSTALL_H_DIR/raygui.h https://raw.githubusercontent.com/raysan5/raygui/$RAYGUI_COMMIT/src/raygui.h

# Build Python bindings for platforms that need custom raylib
if [ -f /TICI ] || [[ -n "${CI:-}" ]]; then

  cd $DIR

  if [ ! -d raylib_python_repo ]; then
    git clone -b master --no-tags https://github.com/commaai/raylib-python-cffi.git raylib_python_repo
  fi

  cd raylib_python_repo

  BINDINGS_COMMIT="f96f6f8a8a1031ebac45fe1bf6b4f4ed778dc7d9"
  git fetch origin $BINDINGS_COMMIT
  git reset --hard $BINDINGS_COMMIT
  git clean -xdff .

  RAYLIB_PLATFORM=$RAYLIB_PLATFORM RAYLIB_INCLUDE_PATH=$INSTALL_H_DIR RAYLIB_LIB_PATH=$INSTALL_DIR python3 setup.py bdist_wheel
  cd $DIR

  rm -rf wheel
  mkdir wheel
  cp raylib_python_repo/dist/*.whl wheel/

  # In CI, install the custom wheel to replace the pip-installed pyray/raylib
  if [[ -n "${CI:-}" ]]; then
    uv pip install --reinstall --no-deps wheel/*.whl
  fi

fi
