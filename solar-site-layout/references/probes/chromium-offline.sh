#!/bin/sh
# Chromium with every non-loopback request sent to a closed local port, so a reference
# scenario cannot reach or depend on external services. Loopback stays direct (Chromium's
# implicit proxy bypass), which is where the locally built reference artifact is served.
exec /opt/pw-browsers/chromium-1243/chrome-linux64/chrome --proxy-server=http://127.0.0.1:9 "$@"
