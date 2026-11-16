#!/usr/bin/env bash
# Zene letöltő eltávolítása Linuxról.
#
#   ./uninstall.sh           a program, a virtuális környezet, az indító parancs, a menübejegyzés és az ikon törlése
#   ./uninstall.sh --purge   ezen felül a beállítások, az előzmények és az archívum is törlődik
#
# Újrafuttatva (vagy telepítés nélkül) is hibátlanul lefut.
set -euo pipefail

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
# A beállítások helye: az XDG_CONFIG_HOME (csak ha abszolút útvonal), különben ~/.config.
case "${XDG_CONFIG_HOME:-}" in
    /*) CONF="$XDG_CONFIG_HOME/zenelero" ;;
    *)  CONF="$HOME/.config/zenelero" ;;
esac

# Gyorsítótár-frissítő: csak ha van ilyen program, és a hibája sosem állítja meg az eltávolítást.
refresh() { command -v "$1" >/dev/null 2>&1 && { "$@" >/dev/null 2>&1 || true; }; return 0; }

rm -rf "$DATA/zenelero"
rm -f "$HOME/.local/bin/zenelero" \
      "$DATA/applications/zenelero.desktop" \
      "$DATA/icons/hicolor/256x256/apps/zenelero.png"

refresh update-desktop-database "$DATA/applications"
refresh kbuildsycoca6
refresh gtk-update-icon-cache -f -t "$DATA/icons/hicolor"
echo "A program eltávolítva."

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$CONF"
    echo "A beállítások és az előzmények is törölve."
else
    echo "A beállítások megmaradtak: $CONF  (törlésük: ./uninstall.sh --purge)"
fi
