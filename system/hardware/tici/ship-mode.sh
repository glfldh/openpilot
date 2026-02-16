#!/bin/sh
[ "$1" = "poweroff" ] && grep -q "mici" /sys/firmware/devicetree/base/model && \
  chmod a+w /sys/class/power_supply/battery/set_ship_mode && \
  echo 1 > /sys/class/power_supply/battery/set_ship_mode
