#!/usr/bin/env bash
# Zene letöltő telepítése Linuxra (KDE Plasma Wayland; Arch-alapú rendszeren: Arch, CachyOS, Garuda).
#
#   ./install.sh            telepítés / frissítés (a beállításokhoz, előzményekhez nem nyúl)
#   ./install.sh --deps     a hiányzó rendszercsomagokat is felrakja (sudo pacman -S --needed)
#
# Hova kerül: ~/.local/share/zenelero/{app,venv}, indító parancs: ~/.local/bin/zenelero,
# alkalmazásmenü-bejegyzés és ikon: ~/.local/share/{applications,icons}. A beállítások helye a
# ~/.config/zenelero (vagy $XDG_CONFIG_HOME/zenelero): ezt sem a telepítés, sem a frissítés nem érinti.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
BASE="$DATA/zenelero"
APP="$BASE/app"
VENV="$BASE/venv"
BIN="$HOME/.local/bin"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mHIBA: %s\033[0m\n' "$*" >&2; exit 1; }
# Gyorsítótár-frissítő: csak ha van ilyen program, és a hibája sosem állítja meg a telepítést.
refresh() { command -v "$1" >/dev/null 2>&1 && { "$@" >/dev/null 2>&1 || true; }; return 0; }
usage() { printf 'Használat: ./install.sh [--deps]\n  --deps   a hiányzó rendszercsomagokat is felrakja (sudo pacman -S --needed)\n'; }

# ---- kapcsolók és a forrás ellenőrzése (bármi létrehozása vagy törlése előtt) ----------------------
WANT_DEPS=0
for arg in "$@"; do
    case "$arg" in
        --deps) WANT_DEPS=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Ismeretlen kapcsoló: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
    esac
done
[ -f "$SRC/zenelero.py" ] && [ -f "$SRC/requirements.txt" ] && [ -f "$SRC/assets/icon.png" ] \
    || die "A kicsomagolt csomagból futtasd az install.sh-t."

# ---- rendszerfüggőségek (bármi létrehozása előtt) ---------------------------------------------
# tk: az ablakok · ffmpeg: átkódolás, címkézés · deno: a yt-dlp YouTube-hoz használja (yt-dlp-ejs)
need=()
if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import tkinter' 2>/dev/null || need+=(tk)
else
    need+=(python tk)
fi
command -v ffmpeg >/dev/null 2>&1 || need+=(ffmpeg)
command -v deno >/dev/null 2>&1 || need+=(deno)

if [ "${#need[@]}" -gt 0 ]; then
    if [ "$WANT_DEPS" = 1 ] && command -v pacman >/dev/null 2>&1; then
        say "Hiányzó csomagok telepítése: ${need[*]}"
        sudo pacman -S --needed --noconfirm "${need[@]}"
    else
        printf 'Hiányzó rendszercsomagok: %s\n' "${need[*]}" >&2
        if command -v pacman >/dev/null 2>&1; then
            printf 'Felrakásuk: sudo pacman -S --needed %s\n   vagy futtasd újra: ./install.sh --deps\n' "${need[*]}" >&2
        fi
        die "Előbb a függőségeket kell felrakni."
    fi
fi

# ---- program + virtuális környezet ---------------------------------------------------------
say "Program másolása: $APP"
mkdir -p "$BASE" "$BIN"
rm -rf "$APP"
mkdir -p "$APP"
cp -r "$SRC"/. "$APP"/
rm -f "$APP/install.sh" "$APP/uninstall.sh" "$APP/zenelero.desktop"

# A venv épségét a benne lévő Python próbája dönti el, nem a létezése: egy rendszer-Python főverzió-frissítés
# után a venv/bin/python az új Pythonra mutat, a csomagok viszont a régi lib/python3.N alatt maradnak.
if ! "$VENV/bin/python" -c 'import pip' >/dev/null 2>&1; then
    say "Virtuális környezet: $VENV"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
fi
say "Python-csomagok (pip)"
"$VENV/bin/pip" install --quiet --upgrade -r "$APP/requirements.txt"

# ---- indító parancs ------------------------------------------------------------------------
cat > "$BIN/zenelero" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$APP/zenelero.py" "\$@"
EOF
chmod +x "$BIN/zenelero"

# ---- alkalmazásmenü-bejegyzés + ikon ---------------------------------------------------------
# Az Exec= értéket sorról sorra cseréljük (nem sed-del), hogy a telepítési út különleges karakterei
# (&, |, \) ne torzítsák; szóköz esetén az Exec-útvonalat idézőjelbe tesszük.
say "Menübejegyzés és ikon"
mkdir -p "$DATA/applications" "$DATA/icons/hicolor/256x256/apps"
exec_path="$BIN/zenelero"
case "$exec_path" in *[[:space:]]*) exec_path="\"$exec_path\"" ;; esac
while IFS= read -r line || [ -n "$line" ]; do
    if [ "$line" = "Exec=@EXEC@" ]; then
        printf 'Exec=%s\n' "$exec_path"
    else
        printf '%s\n' "$line"
    fi
done < "$SRC/zenelero.desktop" > "$DATA/applications/zenelero.desktop"
cp "$SRC/assets/icon.png" "$DATA/icons/hicolor/256x256/apps/zenelero.png"

refresh update-desktop-database "$DATA/applications"
refresh kbuildsycoca6
refresh gtk-update-icon-cache -f -t "$DATA/icons/hicolor"

say "Kész: Zene letöltő"
cat <<EOF

Indítás:        zenelero             (vagy az alkalmazásmenüből: „Zene letöltő")
Eltávolítás:    ./uninstall.sh (a csomagban)
EOF
case ":$PATH:" in *":$BIN:"*) ;; *) printf '\nFIGYELEM: a %s nincs a PATH-ban, a parancs teljes útvonallal indítható: %s/zenelero\n' "$BIN" "$BIN" ;; esac
