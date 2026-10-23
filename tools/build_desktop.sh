#!/bin/bash
# 构建「每日一卦.app」：Swift + WKWebView 外壳，内置网页、引擎与图标。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/每日一卦.app"
RES="$APP/Contents/Resources"
SDK=""
for cand in MacOSX26.5.sdk MacOSX26.sdk MacOSX15.4.sdk; do
  if [ -d "/Library/Developer/CommandLineTools/SDKs/$cand" ]; then
    SDK="/Library/Developer/CommandLineTools/SDKs/$cand"
    break
  fi
done
ENGINE="$ROOT"
PY="$HOME/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3"

if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
fi
if [ -z "${PY:-}" ] || [ ! -x "$PY" ]; then
  echo "找不到 Python 3，无法构建。" >&2
  exit 1
fi
if [ ! -d "$ENGINE/engine" ]; then
  echo "找不到运势引擎：$ENGINE/engine" >&2
  exit 1
fi
if [ -z "$SDK" ] || [ ! -d "$SDK" ]; then
  echo "找不到可用的 macOS Swift SDK。" >&2
  exit 1
fi

echo "→ 清理旧包"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES"

echo "→ 内置网页与引擎"
rsync -a --exclude '__pycache__' --exclude '.DS_Store' "$ROOT/app/" "$RES/app/"
mkdir -p "$RES/自动化任务"
rsync -a --exclude '__pycache__' --exclude '.DS_Store' "$ENGINE/engine/" "$RES/自动化任务/engine/"

if [ -f "$ROOT/data/profile.json" ]; then
  cp "$ROOT/data/profile.json" "$RES/seed-profile.json"
fi
echo "→ 写入 Info.plist"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>zh_CN</string>
  <key>CFBundleDisplayName</key><string>每日一卦</string>
  <key>CFBundleExecutable</key><string>Yigua</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundleIdentifier</key><string>local.yigua.desktop</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>每日一卦</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.lifestyle</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSMultipleInstancesProhibited</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>NSHumanReadableCopyright</key><string>本地运行的传统文化自我参照工具</string>
</dict>
</plist>
PLIST

echo "→ 生成图标"
"$PY" "$ROOT/tools/make_icon.py" "$RES/AppIcon.icns"
rm -rf "$RES/AppIcon.iconset" "$RES/AppIcon.png"

echo "→ 编译 Swift"
swiftc -O -swift-version 5 \
  -sdk "$SDK" -target arm64-apple-macos13.0 \
  -framework Cocoa -framework WebKit \
  "$ROOT/desktop/main.swift" \
  -o "$APP/Contents/MacOS/Yigua"

echo "→ 签名"
codesign --force --deep --sign - "$APP" >/dev/null
xattr -cr "$APP" || true
touch "$APP"

SIZE="$(du -sh "$APP" | awk '{print $1}')"
echo "✓ 已生成：${APP}（${SIZE}）"
