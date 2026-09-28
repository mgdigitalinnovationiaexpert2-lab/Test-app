#!/bin/sh
set -eu
node /opt/mg-cdp-proxy.mjs &
chrome_path="$(node -e 'process.stdout.write(require("playwright").chromium.executablePath())')"
# The stable web image has Xvfb but no xauth. Its Unix socket is private to this container.
export DISPLAY=:99
Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp &
display_attempt=0
until [ -S /tmp/.X11-unix/X99 ]; do
  display_attempt=$((display_attempt + 1))
  [ "$display_attempt" -le 30 ] || exit 1
  sleep 0.1
done
exec \
  "$chrome_path" --no-sandbox --disable-dev-shm-usage \
  --remote-debugging-port=9222 --user-data-dir=/browser-profile about:blank
