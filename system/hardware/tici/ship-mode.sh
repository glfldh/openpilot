#!/bin/sh
echo "ship-mode: called with $1" > /dev/kmsg
[ "$1" = "poweroff" ] && grep -q "mici" /sys/firmware/devicetree/base/model && \
  chmod a+w /sys/class/power_supply/battery/set_ship_mode && \
  echo "ship-mode: chmod ok" > /dev/kmsg && \
  echo 1 > /sys/class/power_supply/battery/set_ship_mode && \
  echo "ship-mode: write ok" > /dev/kmsg