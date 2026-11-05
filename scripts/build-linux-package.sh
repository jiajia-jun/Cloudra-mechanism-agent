#!/usr/bin/env bash
# Build on Linux; end users install the .deb or extract the portable archive.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
if [[ "$(uname -s)" != Linux ]]; then
    printf 'Build Linux packages on Linux, or run the Linux desktop packages workflow.\n' >&2
    exit 1
fi
case "$(uname -m)" in
    x86_64) ARCH=x64; DEB_ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64; DEB_ARCH=arm64 ;;
    *) printf 'Supported Linux package architectures: x86_64 and arm64.\n' >&2; exit 1 ;;
esac
OUTPUT="${1:-$REPO/dist/installers}"
mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"
BUILD="$REPO/build/desktop-linux-$ARCH"
PAYLOAD="$BUILD/Cloudra"
STAGE="$BUILD/debian"
mkdir -p "$BUILD"
rm -rf "$PAYLOAD"
python3 scripts/build_desktop_payload.py --output "$PAYLOAD"
cc -O2 -Wall -Wextra -Werror packaging/linux/launcher.c -o "$PAYLOAD/Cloudra"
cp packaging/linux/launch-cloudra.sh packaging/linux/create_shortcuts.py packaging/linux/cloudra.desktop.in "$PAYLOAD/"
cp docs/assets/Cloudra-logo.svg "$PAYLOAD/cloudra.svg"
chmod 755 "$PAYLOAD/Cloudra" "$PAYLOAD/launch-cloudra.sh"

VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
DEB_VERSION="${VERSION/rc/~rc}"
rm -rf "$STAGE"
mkdir -p "$STAGE/opt" "$STAGE/DEBIAN" "$STAGE/usr/share/applications" "$STAGE/usr/share/doc/cloudra"
cp -a "$PAYLOAD" "$STAGE/opt/cloudra"
cp LICENSE "$STAGE/usr/share/doc/cloudra/copyright"
sed -e 's|@EXEC@|"/opt/cloudra/Cloudra"|g' \
    -e 's|@ICON@|/opt/cloudra/cloudra.svg|g' \
    packaging/linux/cloudra.desktop.in > "$STAGE/usr/share/applications/cloudra.desktop"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: cloudra
Version: $DEB_VERSION
Section: science
Priority: optional
Architecture: $DEB_ARCH
Maintainer: Cloudra Team
Installed-Size: $(du -sk "$PAYLOAD" | cut -f1)
Depends: libc6 (>= 2.28), libstdc++6, ca-certificates, xdg-utils, lsof
Recommends: zenity
Homepage: https://github.com/yyywaa/Cloudra-mechanism-agent
Description: Autonomous chemical reaction mechanism exploration
 Cloudra includes its Python and Node.js runtimes and browser interface.
 Configure model accounts in the interface after opening Cloudra.
EOF
dpkg-deb --root-owner-group --build "$STAGE" "$OUTPUT/Cloudra-$VERSION-linux-$ARCH.deb"
tar -C "$BUILD" -czf "$OUTPUT/Cloudra-$VERSION-linux-$ARCH.tar.gz" Cloudra
printf '\nLinux packages created in %s\n' "$OUTPUT"
