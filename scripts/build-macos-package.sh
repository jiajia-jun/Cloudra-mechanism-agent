#!/usr/bin/env bash
# Build the standard macOS Installer package with an embedded, offline-ready runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${CLOUDRA_PACKAGE_BUILD:-$ROOT/build/macos-package}"
OUTPUT="${CLOUDRA_PACKAGE_OUTPUT:-$ROOT/dist}"
mkdir -p "$BUILD" "$OUTPUT"
VERSION="$(python3 -c 'import tomllib,sys; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$ROOT/pyproject.toml")"
BUNDLE_VERSION="${VERSION%%rc*}"
APP="$BUILD/Cloudra.app"
if [[ -e "$APP" ]]; then
    printf 'Build directory already contains Cloudra.app; choose a clean CLOUDRA_PACKAGE_BUILD.\n' >&2
    exit 1
fi
osacompile -s -o "$APP" "$ROOT/packaging/macos/application.applescript"
if [[ -n "${CLOUDRA_DESKTOP_PAYLOAD:-}" ]]; then
    cp -R "$CLOUDRA_DESKTOP_PAYLOAD" "$APP/Contents/Resources/runtime-staging"
    mv "$APP/Contents/Resources/runtime-staging/"* "$APP/Contents/Resources/"
    rmdir "$APP/Contents/Resources/runtime-staging"
else
    python3 "$ROOT/scripts/build_desktop_payload.py" --output "$BUILD/resources"
    cp -R "$BUILD/resources/"* "$APP/Contents/Resources/"
fi
cp "$ROOT/packaging/macos/Cloudra" "$APP/Contents/MacOS/Cloudra"
chmod +x "$APP/Contents/MacOS/Cloudra"
ICONSET="$BUILD/Cloudra.iconset"
mkdir -p "$ICONSET"
sips -Z 1024 "$ROOT/docs/assets/logo.png" --out "$BUILD/logo-fit.png" >/dev/null
sips --padToHeightWidth 1024 1024 --padColor FFFFFF "$BUILD/logo-fit.png" --out "$BUILD/logo-square.png" >/dev/null
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$BUILD/logo-square.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    doubled=$((size * 2))
    sips -z "$doubled" "$doubled" "$BUILD/logo-square.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Cloudra.icns"
python3 - "$APP/Contents/Info.plist" "$BUNDLE_VERSION" <<'PY'
import plistlib, sys
path = sys.argv[1]
with open(path, 'rb') as stream:
    info = plistlib.load(stream)
info.update(CFBundleIdentifier='io.github.yyywaa.cloudra', CFBundleName='Cloudra',
            CFBundleDisplayName='Cloudra', CFBundleShortVersionString=sys.argv[2], CFBundleVersion=sys.argv[2],
            CFBundleIconFile='Cloudra.icns')
with open(path, 'wb') as stream:
    plistlib.dump(info, stream)
PY
# Ad-hoc signing allows the assembled app to run locally; distribution signing/notarization is separate.
codesign --force --deep --sign - "$APP"
pkgbuild --component "$APP" --install-location /Applications --identifier io.github.yyywaa.cloudra --version "$VERSION" "$BUILD/Cloudra-component.pkg"
cat > "$BUILD/Distribution.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>Cloudra</title>
  <organization>io.github.yyywaa</organization>
  <welcome file="welcome.html"/>
  <license file="LICENSE.txt"/>
  <conclusion file="conclusion.html"/>
  <options customize="never" require-scripts="false"/>
  <domains enable_localSystem="true"/>
  <choices-outline><line choice="cloudra"/></choices-outline>
  <choice id="cloudra" title="Cloudra" visible="false"><pkg-ref id="io.github.yyywaa.cloudra"/></choice>
  <pkg-ref id="io.github.yyywaa.cloudra" version="$VERSION">Cloudra-component.pkg</pkg-ref>
</installer-gui-script>
XML
mkdir -p "$BUILD/installer-resources"
cp "$ROOT/packaging/macos/welcome.html" "$ROOT/packaging/macos/conclusion.html" "$BUILD/installer-resources/"
cp "$ROOT/LICENSE" "$BUILD/installer-resources/LICENSE.txt"
cp "$ROOT/docs/assets/logo.png" "$BUILD/installer-resources/logo.png"
PACKAGE="$OUTPUT/Cloudra-$VERSION-macos-$(uname -m).pkg"
productbuild --distribution "$BUILD/Distribution.xml" --package-path "$BUILD" --resources "$BUILD/installer-resources" "$PACKAGE"
cp "$ROOT/packaging/macos/Unblock-Cloudra.command" "$OUTPUT/Unblock-Cloudra.command"
chmod +x "$OUTPUT/Unblock-Cloudra.command"
printf '\nInstaller ready: %s\n' "$PACKAGE"
