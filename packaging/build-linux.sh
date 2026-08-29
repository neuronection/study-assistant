#!/usr/bin/env bash
# Build Linux packages for Study Assistant: PyInstaller onedir + optional .deb / .AppImage.
# Usage: packaging/build-linux.sh [deb|appimage|bundle|all] [version]
#   bundle   only the PyInstaller onedir tree (backend/dist/studyassistant)
#   deb      bundle + .deb (needs dpkg-deb; target needs libwebkit2gtk-4.1)
#   appimage bundle + AppImage (needs appimagetool; fully self-contained)
#   all      bundle + deb + appimage (default)
# Env: APPIMAGETOOL=/path/to/appimagetool (auto-detected on PATH), SA_ONEFILE=0 is forced for Linux.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="studyassistant"
TARGET="${1:-all}"
VERSION="${2:-}"
BUNDLE="$ROOT/backend/dist/$APP"
WORK="$ROOT/packaging/_build"

if [[ -z "$VERSION" ]]; then
  VERSION="$(uv run --directory "$ROOT/backend" python -c 'import app; print(app.__version__)')"
fi

if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  echo "==> frontend/dist missing, building"
  (cd "$ROOT" && pnpm --filter frontend build)
fi

echo "==> PyInstaller onedir (version $VERSION)"
uv run --directory "$ROOT/backend" pyinstaller --clean --noconfirm \
  --distpath "$ROOT/backend/dist" --workpath "$WORK" \
  "$ROOT/packaging/studyassistant.spec"

if [[ "$TARGET" == "bundle" ]]; then
  echo "==> Done: $BUNDLE"
  exit 0
fi

install_bundle() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest"
  cp -r "$BUNDLE/." "$dest/"
}

if [[ "$TARGET" == "deb" || "$TARGET" == "all" ]]; then
  STAGE="$ROOT/packaging/_deb"
  echo "==> Assembling .deb tree"
  rm -rf "$STAGE"
  mkdir -p "$STAGE/usr/lib/$APP" "$STAGE/usr/bin" \
    "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE/DEBIAN"
  install_bundle "$STAGE/usr/lib/$APP"

  echo "==> Stripping bundled GUI stack from deb stage (system copies must win)"
  INTERNAL="$STAGE/usr/lib/$APP/_internal"
  if [[ -d "$INTERNAL" ]]; then
    find "$INTERNAL" -maxdepth 1 -type f -name 'lib*.so*' \
      ! -name 'libpython3*' ! -name 'libmupdf*' ! -name 'libmupdfcpp*' \
      ! -name 'libssl*' ! -name 'libcrypto*' ! -name 'libsqlite3*' ! -name 'libffi*' \
      ! -name 'libz.so*' ! -name 'libzstd*' ! -name 'liblzma*' ! -name 'libbz2*' \
      ! -name 'libexpat*' ! -name 'libgcc_s*' ! -name 'libreadline*' \
      ! -name 'libtinfo*' ! -name 'libncursesw*' -delete
    rm -rf "$INTERNAL/gio_modules"
  fi

  cat > "$STAGE/usr/bin/$APP" <<EOF
#!/usr/bin/env bash
exec /usr/lib/$APP/$APP "\$@"
EOF
  chmod +x "$STAGE/usr/bin/$APP"

  cat > "$STAGE/usr/share/applications/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Study Assistant
Comment=AI-powered local-first study workbench
Exec=$APP
Icon=$APP
Terminal=false
Categories=Education;Science;Office;
Keywords=study;notes;flashcards;quiz;tutor;
StartupWMClass=$APP
EOF

  cp "$ROOT/packaging/icon.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/$APP.svg"

  cat > "$STAGE/DEBIAN/control" <<EOF
Package: $APP
Version: $VERSION
Section: education
Priority: optional
Architecture: amd64
Maintainer: StudyAssistant <dev@studyassistant.local>
Depends: libgtk-3-0, libwebkit2gtk-4.1-0, libglib2.0-0, libgirepository-1.0-1
Description: AI-powered, local-first desktop study workbench
 Math-first study workbench for upload, outline, quiz, tutor, notes and
 flashcards. Runs fully offline except optional cloud OCR/LLM calls.
EOF

  DEB="$ROOT/packaging/${APP}_${VERSION}_amd64.deb"
  dpkg-deb --build --root-owner-group "$STAGE" "$DEB"
  echo "==> Done: $DEB"
fi

if [[ "$TARGET" == "appimage" || "$TARGET" == "all" ]]; then
  APPDIR="$ROOT/packaging/_appimage/AppDir"
  EXTRA="$APPDIR/usr/lib/sa-extra"
  echo "==> Assembling AppDir"
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps"
  install_bundle "$APPDIR/usr/lib/$APP"

  collect_libs() {
    mkdir -p "$EXTRA"
    local -a queue=()
    local f dep dep_base target
    while IFS= read -r f; do queue+=("$f"); done < <(find "$APPDIR/usr/lib/$APP" -type f \( -name '*.so' -o -name '*.so.*' \))
    local name path
    for name in libwebkit2gtk-4.1.so.0 libjavascriptcoregtk-4.1.so.0 libgtk-3.so.0 \
      libgdk_pixbuf-2.0.so.0 libgirepository-1.0.so.1 libstdc++.so.6; do
      path="$(ldconfig -p | awk -v n="$name" '$1==n {print $NF; exit}')"
      [[ -n "$path" ]] && queue+=("$path")
    done

    local -A copied=()
    local -A bundled=()
    while IFS= read -r f; do bundled["$(basename "$f")"]=1; done < <(find "$APPDIR/usr/lib/$APP" -type f \( -name '*.so' -o -name '*.so.*' \))

    local exclude='^(ld-linux|libc\.|libm\.|libdl\.|libpthread\.|librt\.|libresolv\.|libnss_|libnsl|libcrypt|libutil\.|libanl\.|libBrokenLocale|libSegFault|libcidn|libSrpc|linux-vdso)'
    local -a pending=("${queue[@]}")
    while [[ ${#pending[@]} -gt 0 ]]; do
      f="${pending[0]}"; pending=("${pending[@]:1}")
      [[ -z "$f" || ! -f "$f" ]] && continue
      dep_base="$(basename "$f")"
      if [[ ! "$dep_base" =~ $exclude && -z "${bundled[$dep_base]:-}" && -z "${copied[$dep_base]:-}" ]]; then
        cp -L "$f" "$EXTRA/$dep_base"
        copied["$dep_base"]=1
        pending+=("$EXTRA/$dep_base")
      fi
      while IFS= read -r dep; do
        dep_base="$(basename "$dep")"
        [[ -z "$dep" ]] && continue
        if [[ "$dep_base" =~ $exclude ]]; then continue; fi
        if [[ -n "${bundled[$dep_base]:-}" || -n "${copied[$dep_base]:-}" ]]; then continue; fi
        target="$EXTRA/$dep_base"
        cp -L "$dep" "$target"
        copied["$dep_base"]=1
        pending+=("$target")
      done < <(ldd "$f" 2>/dev/null | awk '/=> \// {print $3} /^\// {print $1}')
    done
  }
  collect_libs

  local_loader_dir=""
  for d in /usr/lib/x86_64-linux-gnu /usr/lib64 /usr/lib; do
    for ld in "$d"/gdk-pixbuf-2.0/*/loaders; do
      [[ -d "$ld" ]] && local_loader_dir="$ld" && break 2
    done
  done
  if [[ -n "$local_loader_dir" ]] && command -v gdk-pixbuf-query-loaders >/dev/null; then
    mkdir -p "$EXTRA/pixbuf/loaders"
    cp -L "$local_loader_dir"/*.so "$EXTRA/pixbuf/loaders/" 2>/dev/null || true
    GDK_PIXBUF_MODULEDIR="$EXTRA/pixbuf/loaders" gdk-pixbuf-query-loaders \
      | sed "s|$EXTRA|@APPDIR@/usr/lib/sa-extra|g" > "$EXTRA/pixbuf/loaders.cache.in"
  fi

  cp "$ROOT/packaging/icon.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APP.svg"
  cp "$ROOT/packaging/icon.svg" "$APPDIR/$APP.svg"
  cat > "$APPDIR/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Study Assistant
Comment=AI-powered local-first study workbench
Exec=AppRun
Icon=$APP
Terminal=false
Categories=Education;Science;Office;
Keywords=study;notes;flashcards;quiz;tutor;
StartupWMClass=$APP
EOF

  cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="$APPDIR/usr/lib/sa-extra${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cache_src="$APPDIR/usr/lib/sa-extra/pixbuf/loaders.cache.in"
if [[ -f "$cache_src" ]]; then
  cache_gen="$(mktemp)"
  sed "s|@APPDIR@|$APPDIR|g" "$cache_src" > "$cache_gen"
  export GDK_PIXBUF_MODULE_FILE="$cache_gen"
fi
exec "$APPDIR/usr/lib/studyassistant/studyassistant" "$@"
EOF
  chmod +x "$APPDIR/AppRun"

  APPIMAGETOOL_BIN="${APPIMAGETOOL:-appimagetool}"
  if [[ ! -x "$APPIMAGETOOL_BIN" ]] && ! command -v "$APPIMAGETOOL_BIN" >/dev/null; then
    echo "appimagetool not found; set APPIMAGETOOL=/path/to/appimagetool" >&2
    exit 1
  fi
  TOOL_ARGS=()
  if file "$APPIMAGETOOL_BIN" 2>/dev/null | grep -qi "appimage"; then
    TOOL_ARGS=(--appimage-extract-and-run)
  fi
  OUT="$ROOT/packaging/StudyAssistant-$VERSION-x86_64.AppImage"
  "$APPIMAGETOOL_BIN" "${TOOL_ARGS[@]}" "$APPDIR" "$OUT"
  echo "==> Done: $OUT"
fi
