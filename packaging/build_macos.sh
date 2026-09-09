#!/bin/sh
set -eu

PYTHON_BIN=${PYTHON_BIN:-venv/bin/python}
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean packaging/interview-helper.spec

if [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
  codesign --force --deep --options runtime --entitlements packaging/entitlements.plist \
    --sign "$APPLE_SIGNING_IDENTITY" "dist/Interview Helper.app"
  codesign --verify --deep --strict --verbose=2 "dist/Interview Helper.app"
else
  echo "Unsigned app built. Set APPLE_SIGNING_IDENTITY to produce a signed build."
fi

if [ "${RUN_SMOKE_TEST:-0}" = "1" ]; then
  QT_QPA_PLATFORM=offscreen "dist/Interview Helper.app/Contents/MacOS/Interview Helper" --smoke-test
fi
