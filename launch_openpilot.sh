#!/usr/bin/env bash

# rm -rf tinygrad_repo
# git submodule sync
# git submodule update --init --recursive
export USBGPU=1
exec ./launch_chffrplus.sh
