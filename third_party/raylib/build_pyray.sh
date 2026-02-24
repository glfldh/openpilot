#!/usr/bin/env bash
# Build a pyray wheel with GLFW null platform for headless rendering.
# The pip pyray package ships with GLFW that doesn't have null platform linked in.
# This rebuilds raylib with ONLY the null platform (no X11/Wayland) to avoid
# symbol conflicts in raylib's unity build, then creates a replacement wheel.
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
cd "$DIR"

SUDO=""
if [[ ! $(id -u) -eq 0 ]]; then
  if command -v sudo &>/dev/null; then
    SUDO="sudo"
  fi
fi

$SUDO apt-get install -y --no-install-recommends libosmesa6-dev

# Use same raylib source and commit as build.sh
if [ ! -d raylib_repo ]; then
  git clone -b master --no-tags https://github.com/commaai/raylib.git raylib_repo
fi

cd raylib_repo
COMMIT=3425bd9d1fb292ede4d80f97a1f4f258f614cffc
git fetch origin $COMMIT
git reset --hard $COMMIT
git clean -xdff .

# --- Patch 1: rglfw.c - Build null-only on Linux (no X11/Wayland) ---
# Remove the X11/Wayland requirement check and replace the Linux block
# with null platform includes only. This avoids symbol conflicts between
# x11_window.c and null_window.c in raylib's unity build.
cat > /tmp/rglfw_linux_patch.py << 'PYEOF'
import re

with open("src/rglfw.c") as f:
    content = f.read()

# Remove the error check that requires X11 or Wayland
content = content.replace(
    '#if defined(__linux__)\n'
    '    #if !defined(_GLFW_WAYLAND) && !defined(_GLFW_X11)\n'
    '        #error "Cannot disable Wayland and X11 at the same time"\n'
    '    #endif\n'
    '#endif',
    '#if defined(__linux__)\n'
    '    #if !defined(_GLFW_WAYLAND) && !defined(_GLFW_X11) && !defined(_GLFW_NULL)\n'
    '        #error "Cannot disable Wayland, X11, and Null at the same time"\n'
    '    #endif\n'
    '#endif'
)

# Add null platform includes to the Linux block
old_linux_block = '''#if defined(__linux__)
    #include "external/glfw/src/posix_module.c"
    #include "external/glfw/src/posix_thread.c"
    #include "external/glfw/src/posix_time.c"
    #include "external/glfw/src/posix_poll.c"
    #include "external/glfw/src/linux_joystick.c"
    #include "external/glfw/src/xkb_unicode.c"

    #include "external/glfw/src/egl_context.c"
    #include "external/glfw/src/osmesa_context.c"

    #if defined(_GLFW_WAYLAND)
        #include "external/glfw/src/wl_init.c"
        #include "external/glfw/src/wl_monitor.c"
        #include "external/glfw/src/wl_window.c"
    #endif
    #if defined(_GLFW_X11)
        #include "external/glfw/src/x11_init.c"
        #include "external/glfw/src/x11_monitor.c"
        #include "external/glfw/src/x11_window.c"
        #include "external/glfw/src/glx_context.c"
    #endif
#endif'''

new_linux_block = '''#if defined(__linux__)
    #include "external/glfw/src/posix_module.c"
    #include "external/glfw/src/posix_thread.c"
    #include "external/glfw/src/posix_time.c"
    #include "external/glfw/src/posix_poll.c"
    #include "external/glfw/src/linux_joystick.c"
    #include "external/glfw/src/xkb_unicode.c"

    #include "external/glfw/src/egl_context.c"
    #include "external/glfw/src/osmesa_context.c"

    #if defined(_GLFW_WAYLAND)
        #include "external/glfw/src/wl_init.c"
        #include "external/glfw/src/wl_monitor.c"
        #include "external/glfw/src/wl_window.c"
    #endif
    #if defined(_GLFW_X11)
        #include "external/glfw/src/x11_init.c"
        #include "external/glfw/src/x11_monitor.c"
        #include "external/glfw/src/x11_window.c"
        #include "external/glfw/src/glx_context.c"
    #endif
    #if defined(_GLFW_NULL)
        #include "external/glfw/src/null_init.c"
        #include "external/glfw/src/null_monitor.c"
        #include "external/glfw/src/null_window.c"
        #include "external/glfw/src/null_joystick.c"
    #endif
#endif'''

content = content.replace(old_linux_block, new_linux_block)

with open("src/rglfw.c", "w") as f:
    f.write(content)

print("Patched rglfw.c successfully")
PYEOF
python3 /tmp/rglfw_linux_patch.py

# --- Patch 2: platform.c - Add null to supportedPlatforms[] ---
cat > /tmp/platform_patch.py << 'PYEOF'
with open("src/external/glfw/src/platform.c") as f:
    content = f.read()

# Add _GLFW_NULL to the supportedPlatforms array
old = '''#if defined(_GLFW_X11)
    { GLFW_PLATFORM_X11, _glfwConnectX11 },
#endif
};'''

new = '''#if defined(_GLFW_X11)
    { GLFW_PLATFORM_X11, _glfwConnectX11 },
#endif
#if defined(_GLFW_NULL)
    { GLFW_PLATFORM_NULL, _glfwConnectNull },
#endif
};'''

content = content.replace(old, new)

with open("src/external/glfw/src/platform.c", "w") as f:
    f.write(content)

print("Patched platform.c successfully")
PYEOF
python3 /tmp/platform_patch.py

# Build raylib with null-only GLFW (no X11/Wayland to avoid symbol conflicts)
BUILD_DIR="$DIR/raylib_repo/_build"
mkdir -p "$BUILD_DIR"
cd src
make -j$(nproc) PLATFORM=PLATFORM_DESKTOP GLFW_LINUX_ENABLE_X11=FALSE CUSTOM_CFLAGS="-D_GLFW_NULL" RAYLIB_RELEASE_PATH="$BUILD_DIR"

INCLUDE_DIR="$BUILD_DIR/include"
mkdir -p "$INCLUDE_DIR"
cp raylib.h raymath.h rlgl.h "$INCLUDE_DIR/"

# Download raygui header (same commit as build.sh)
RAYGUI_COMMIT="76b36b597edb70ffaf96f046076adc20d67e7827"
curl -fsSLo "$INCLUDE_DIR/raygui.h" "https://raw.githubusercontent.com/raysan5/raygui/$RAYGUI_COMMIT/src/raygui.h"

# Build Python bindings (same approach as build.sh for TICI)
cd "$DIR"
if [ ! -d raylib_python_repo ]; then
  git clone -b master --no-tags https://github.com/commaai/raylib-python-cffi.git raylib_python_repo
fi
cd raylib_python_repo
BINDINGS_COMMIT=a0710d95af3c12fd7f4b639589be9a13dad93cb6
git fetch origin $BINDINGS_COMMIT
git reset --hard $BINDINGS_COMMIT
git clean -xdff .

RAYLIB_PLATFORM=PLATFORM_DESKTOP \
  RAYLIB_INCLUDE_PATH="$INCLUDE_DIR" \
  RAYLIB_LIB_PATH="$BUILD_DIR" \
  python setup.py bdist_wheel

uv pip install dist/*.whl --force-reinstall --no-deps

echo "Headless pyray wheel built and installed successfully"
