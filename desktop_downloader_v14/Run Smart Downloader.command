#!/bin/sh
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$APP_DIR/run_smart_downloader.sh"
