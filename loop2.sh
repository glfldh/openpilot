#!/usr/bin/env bash
set -u

pkill -f watch3
pkill -f compressed_vipc

BIG=1 /home/batman/openpilot/selfdrive/ui/watch3.py &

on_device() {
  local serial="$1"

  adb -s "$serial" shell 'su - comma -c "source /etc/profile && tmux kill-server"'

  case "$serial" in
    cdea8611) n=1 ;;
    e3a64917)  n=2 ;;
    63c61c84)  n=3 ;;
    *)        n=0 ;;
  esac

  PORTS="51336 57332 42305"
  for p in $PORTS; do
    adb -s $serial forward tcp:$((p + n)) tcp:$p
  done

  PORT_OFFSET=$n /home/batman/openpilot/tools/camerastream/compressed_vipc.py 127.0.0.1 --server="focusing_$n" &

  adb -s "$serial" push camera.sh /data
  adb -s "$serial" shell 'su - comma -c "source /etc/profile && sudo chown comma: /data/camera.sh && chmod +x /data/camera.sh"'
  adb -s "$serial" shell 'su - comma -c "source /etc/profile && /data/camera.sh"'
  pkill -f "focusing_$n"
}

rm -f "/tmp/restart_cameras"

declare -A connected=()

while true; do

  # connected
  declare -A now=()
  while read -r serial state; do
    [[ -z "${serial:-}" ]] && continue
    [[ "${state:-}" != "device" ]] && continue
    now["$serial"]=1
  done < <(adb devices | tail -n +2)

  # disconnected
  for serial in "${!connected[@]}"; do
    [[ -z "${now[$serial]+x}" ]] && unset "connected[$serial]" && echo "Disconnected: $serial"
  done

  # new connected
  for serial in "${!now[@]}"; do
    if [[ -z "${connected[$serial]+x}" ]]; then
      connected["$serial"]=1
      echo "Connected: $serial"
      on_device "$serial" &
    fi
  done

  if [ -e "/tmp/kill_cameras" ]; then
    rm -f "/tmp/kill_cameras"
    echo "KILLING ADB SHELLS"
    for serial in "${!now[@]}"; do
      pkill -9 -f "adb -s $serial shell su - comma -c \"source /etc/profile && /data/camera.sh\""
    done
    sleep 0.5
    for serial in "${!now[@]}"; do
      adb -s "$serial" shell 'pkill -9 -f camerad'
      adb -s "$serial" shell 'pkill -9 -f encoderd'
      adb -s "$serial" shell 'pkill -9 -f bridge'
    done
    touch "/tmp/killed_cameras"
  fi


  if [[ -e "/tmp/start_cameras" && -e "/tmp/killed_cameras" ]]; then
    rm -f "/tmp/killed_cameras"
    rm -f "/tmp/start_cameras"
    echo "RESTARTING CAMERAS"
    for serial in "${!now[@]}"; do
      on_device "$serial" &
    done
  fi

  sleep 0.1
done
