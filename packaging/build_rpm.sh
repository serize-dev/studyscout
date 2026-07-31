#!/usr/bin/env bash
# ===========================================================================
#  Build a self-contained STUDY//SCOUT .rpm for Fedora (x86_64).
#
#  PyInstaller freezes the app into ONE binary bundling its own Python +
#  every dependency; rpmbuild wraps it. On the Fedora box:
#
#      sudo dnf install ./studyscout-1.0.0-1.x86_64.rpm
#      studyscout
#
#  Usage:   bash packaging/build_rpm.sh
#  Output:  dist/rpm/RPMS/x86_64/studyscout-<v>-1.x86_64.rpm
#
#  Needs: rpmbuild (native, or point RPM_TOOLS at an extracted rpm tree —
#  see the fallback below), binutils for PyInstaller.
# ===========================================================================
set -euo pipefail

VERSION="1.5.2"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
echo "▸ python: $PY"

echo "▸ ensuring build deps (pyinstaller)…"
"$PY" -m pip install --quiet --upgrade pyinstaller >/dev/null

echo "▸ freezing binary with PyInstaller…"
rm -rf build dist/studyscout "$ROOT/studyscout.spec"
"$PY" -m PyInstaller \
    --name studyscout \
    --onefile \
    --noconfirm \
    --clean \
    --paths src \
    --add-data "src/studyscout/tui/styles.tcss:studyscout/tui" \
    --collect-all textual \
    --collect-all rich \
    --collect-all anthropic \
    --collect-submodules studyscout \
    --console \
    packaging/entry.py
rm -f "$ROOT/studyscout.spec"          # PyInstaller's spec, not the RPM one

BIN="dist/studyscout"
[ -x "$BIN" ] || { echo "✗ build failed: $BIN missing"; exit 1; }
echo "▸ smoke-testing frozen binary…"
"$BIN" --version
"$BIN" where || true

# ---- rpmbuild: native, or a locally-extracted Debian rpm tree ------------ #
if command -v rpmbuild >/dev/null 2>&1 && [ -z "${RPM_TOOLS:-}" ]; then
    RPMBUILD=(rpmbuild)
else
    RPM_TOOLS="${RPM_TOOLS:?rpmbuild not found — set RPM_TOOLS to an extracted rpm tree (dpkg -x rpm*.deb root)}"
    export LD_LIBRARY_PATH="$RPM_TOOLS/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
    RPMBUILD=("$RPM_TOOLS/usr/bin/rpmbuild"
              --rcfile "$RPM_TOOLS/usr/lib/rpm/rpmrc"
              --macros "$RPM_TOOLS/usr/lib/rpm/macros:$RPM_TOOLS/usr/lib/rpm/platform/x86_64-linux/macros")
    echo "▸ using extracted rpm tools at $RPM_TOOLS"
fi

echo "▸ assembling rpm tree…"
TOP="$ROOT/dist/rpm"
rm -rf "$TOP"
mkdir -p "$TOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
install -m 0755 "$BIN" "$TOP/SOURCES/studyscout"
install -m 0644 README.md "$TOP/SOURCES/README.md"
install -m 0644 HANDBOOK.md "$TOP/SOURCES/HANDBOOK.md"
for sz in 48 64 128 256; do
    install -m 0644 "packaging/icons/studyscout_${sz}.png" "$TOP/SOURCES/studyscout_${sz}.png"
done

cat > "$TOP/SOURCES/studyscout.desktop" <<'EOF'
[Desktop Entry]
Name=Study Scout
Comment=Phosphor-green clinical-trials BD intel terminal
Exec=studyscout
Icon=studyscout
Terminal=true
Type=Application
Categories=Utility;Office;
EOF

"${RPMBUILD[@]}" -bb \
    --define "_topdir $TOP" \
    --define "scout_version $VERSION" \
    --define "_dbpath $TOP/rpmdb" \
    ${RPM_TOOLS:+--define "_fileattrsdir ${RPM_TOOLS}/usr/lib/rpm/fileattrs"} \
    packaging/studyscout.spec

RPM="$(ls "$TOP"/RPMS/x86_64/studyscout-*.rpm)"
echo
echo "✓ built: $RPM"
echo "Install on Fedora:   sudo dnf install ./$( realpath --relative-to="$ROOT" "$RPM" )"
echo "Then run:            studyscout"
