# Linux-támogatás – terv

Állapot: jóváhagyásra vár. Dátum: 2026-11-16.

## Cél és miért

A Zene letöltő ma csak Windowson fut telepített alkalmazásként. A cél, hogy **ugyanaz a program Linuxon is „rendes
alkalmazás” legyen**, ahogy a Képprofil: telepíthető, megjelenik az alkalmazásmenüben ikonnal, van saját parancsa
(`zenelero`), és eltávolítható. A célgép az, amin a Képprofil is fut: **Arch-alapú rendszer, KDE Plasma, Wayland**.

Mit jelent a siker:
- Egy `.tar.gz`-ból egyetlen `./install.sh --deps` paranccsal felkerül, a menüből indul, és letölt (YouTube, Spotify-lista).
- A Windowsos telepítő és működés **nem változik**: ugyanaz a viselkedés, ugyanazok a tesztek zöldek.
- Egy kódbázis a `main` ágon, **nincs külön Linux-ág** (a javítások nem duplázódnak).

## Nem cél / ne legyen

- Más disztró (apt, dnf) vagy más asztali környezet: az `install.sh` Arch/pacman alapú, mint a Képprofilé.
- PKGBUILD, AppImage, PyInstaller-csomag Linuxra (lásd Megközelítések).
- Automatikus heti yt-dlp-frissítés Linuxon: csak a kézi **Frissítés** gomb (lásd Döntések).
- A `gui()` (906 soros függvény) szétszedése: ez külön, későbbi munka. Itt csak a platformfüggő függvények költöznek.
- Natív Wayland-ablak: a customtkinter/tk XWaylanden fut, ez elfogadott.

Kudarcnak számít, ha: a Windowsos viselkedés bárhol eltér, vagy a Linuxos telepítés kézi pip/ffmpeg-lépéseket kér a
felhasználótól, vagy a Linux-támogatás miatt a kódban két, szétváló másolat keletkezik.

## Megközelítések (a választás: A + kis platformmodulok)

| | Mit jelent | Mellette | Ellene |
|---|---|---|---|
| **A. tar.gz + install.sh** (választott) | `~/.local/share/zenelero/{app,venv}`, parancs a `~/.local/bin`-ben, `.desktop` + ikon | Windowsról építhető, a Képprofil bevált mintája, `--deps` pacmannel | a pip-csomagok telepítéskor töltődnek le; az eltávolítást a script végzi |
| B. PKGBUILD | natív Arch-csomag | pacman kezeli a függőséget és az eltávolítást | csak Archon építhető, a spotDL AUR-csomagjától függ |
| C. PyInstaller / AppImage Linuxon | önálló bináris | nincs telepítési függőség | csak Linuxon építhető, nagy, a tk Waylanden kényes |

Kód-szétválasztás: kis platformmodulok (választott) vs. `if sys.platform` szétszórva a `zenelero.py`-ban. A modulos megoldás
azért jobb, mert a `zenelero.py` többi része (felület, letöltési logika) nem tud a platformról, és a Képprofilban is így van.

## Felépítés

### Platformmodulok
- `plat.py` – választó: `win32` → `plat_windows`, különben `plat_linux`; a `zenelero.py` ebből importál. (A név nem
  `platform.py`, mert az a standard könyvtár modulját árnyékolná.)
- `plat_windows.py` – a mai viselkedés **változtatás nélkül** átmozgatva.
- `plat_linux.py` – új.

A modul felülete (a nevek javaslatok, a builder pontosíthatja, a viselkedés a lényeg):

| Felület | Windows (mai) | Linux (új) |
|---|---|---|
| adatmappa | `%APPDATA%\Zene letöltő` (csomagolt), a forrásmappa (fejlesztői) | `$XDG_CONFIG_HOME/zenelero` (`~/.config/zenelero`): `settings.json`, `history.json`, `archivum/` |
| eszközparancsok (`yt-dlp`, `spotdl`, `spotify_list`) | csomagolt: `ZeneLetolto.exe --tool …`; fejlesztői: `.venv\Scripts\python.exe -m …` | `sys.executable -m yt_dlp` / `-m spotdl` / `spotify_list.py` (a telepített venv Pythonja) |
| `ffmpeg` / `deno` keresése és a futtatható neve | a telepítő `bin` mappája, PATH, WinGet; `ffmpeg.exe` (a spotDL `--ffmpeg` argumentuma ma fixen `ffmpeg.exe`-t fűz hozzá) | PATH (a pacman csomagjai); `ffmpeg` |
| gyerekfolyamat indítása | `creationflags=CREATE_NO_WINDOW` | `start_new_session=True` (új folyamatcsoport) |
| leállítás (`kill_tree`) | `taskkill /T /F` | `os.killpg(pgid, SIGTERM)`, rövid várakozás után `SIGKILL` |
| ablakrejtés (`hide_child_windows`, `fix_stdio`) | a mai javítás | nincs teendő (üres) |
| mappa megnyitása / fájl kijelölése | `os.startfile`, `explorer /select` | `xdg-open`; fájl kijelölése `dolphin --select`, ha van, különben a mappa `xdg-open`-nel |
| ablak-ikon | `iconbitmap(icon.ico)` | `iconphoto` PNG-ből (`assets/icon.png`) |
| naplóbetű | `Consolas` | `monospace` |

A `zenelero.py`-ban marad minden más. A meglévő `FROZEN` ág és a Windowsos `--tool` belépő a Windowsos modulba/kódba
tartozik; Linuxon nincs `--tool`, mert nincs csomagolt exe.

### Frissítés Linuxon
A **Frissítés** gomb a már meglévő nem-csomagolt ágat használja: `sys.executable -m pip install -U yt-dlp spotdl` a
telepített venvben (a venv a felhasználó mappájában van, nem kell hozzá root). Az automatikus heti ellenőrzés
(`auto_update_start`) csak a csomagolt Windowsos változatban fut, ez nem változik.

### Csomagolás
- `build_linux.py` (Windowson futtatva, a Képprofil `build_linux.py`-jának mintájára): `out/Zenelero-linux-<verzió>.tar.gz`,
  mappa: `zenelero-<verzió>/`. Kimarad belőle a Windowsos réteg (`plat_windows.py`, `build.ps1`, `build_installer/`,
  `zenelero.bat`, tesztek). A csomagoló ellenőrzi, hogy minden betett modul lefordul és nincs hiányzó helyi import;
  a CRLF sortöréseket LF-re cseréli; másolat a `Documents\telepitok` mappába, mint a Windowsos telepítőnél.
- `linux/install.sh`: `python3`, `tk`, `ffmpeg`, `deno` meglétét ellenőrzi; `--deps` esetén `sudo pacman -S --needed`.
  A programot a `~/.local/share/zenelero/app` alá másolja, `venv`-et készít a `requirements.txt`-ből, létrehozza a
  `~/.local/bin/zenelero` parancsot, a `.desktop` fájlt (`~/.local/share/applications/zenelero.desktop`) és az ikont
  (`~/.local/share/icons/hicolor/256x256/apps/zenelero.png`), majd frissíti az ikon-/menügyorsítótárat, ha van rá eszköz.
  Újrafuttatva frissít, a `~/.config/zenelero/` beállításaihoz nem nyúl.
- `linux/uninstall.sh`: eltávolítja a programot, a parancsot, a `.desktop`-ot és az ikont; `--purge` a beállításokat is.
- `requirements.txt` (új): `customtkinter`, `pillow`, `spotdl`, `yt-dlp[default]` (az `[default]` hozza a deno-s
  YouTube-kihíváshoz kellő `yt-dlp-ejs`-t). A többit (ytmusicapi, spotipyfree stb.) a spotDL húzza be; a builder ellenőrizze
  a tiszta venvben, hogy tényleg minden importálható.
- Új: `assets/icon.png` (a meglévő 256×256-os `icon-preview.png` alapján) és `docs`/`LINUX.md`: telepítés, fájlhelyek,
  kézi próbák listája, ismert korlátok.
- A `README.md` kapjon „Linux” részt, és az „Állapot” szerint a Linuxos változat valódi gépen tesztelve legyen, ha lett.

## Döntések

A felhasználó döntései:
- Egy kódbázis, `main` ág; a csomagolás az **A. megközelítés**; **kis platformmodulok**.
- Célgép: ugyanaz, mint a Képprofilé (Arch, KDE Plasma Wayland).

A saját döntéseim (javítható):
- A `.desktop` és az ikon az `install.sh`-ból jön, nem a program első indításából.
- Adatmappa Linuxon: `~/.config/zenelero/`; zene alapból `~/Music/Zenelero/` (a mai `DEFAULT_OUT`).
- Linuxon nincs automatikus heti yt-dlp-frissítés, csak a gomb.
- Linuxon nincs `--tool` belépő és nincs ablakrejtés.
- A tesztek nem kerülnek a Linux-csomagba.

## Ellenőrzés és kockázatok

Windowson (itt) bizonyítható:
- A meglévő tesztek zöldek; a Windowsos csomagolt eszköz viselkedése változatlan (a `ZeneLetolto.exe`-ből épített telepítő
  ugyanúgy működik: letöltés, nincs felugró ablak) – a platformmodulok kivágása ezt törhetné el.
- A `plat_linux` tiszta logikája mockolt környezetben: útvonalak (`XDG_CONFIG_HOME` megléte/hiánya), parancsépítés,
  fájl-kijelölés ágai (`dolphin` van/nincs).
- `build_linux.py` lefut, a tar tartalma és a sortörések rendben vannak, `bash -n` az `install.sh`/`uninstall.sh`-ra.

**Csak a Linuxos gépen** bizonyítható (itt nincs WSL, ezt nem állítom, amíg nem futott):
- az `install.sh --deps` végigmegy, az alkalmazás a menüből indul, az ikon látszik;
- YouTube- és Spotify-letöltés, a Leállítás gomb tényleg megöli a `deno`/`ffmpeg` gyerekeket (`killpg`);
- Frissítés gomb (pip); mappamegnyitás, fájlkijelölés Dolphinban;
- a customtkinter megjelenése XWaylanden (skálázás, betűk), a Python-verzió és a spotDL kompatibilitása az Arch aktuális Pythonján;
- a vágólap-link automatikus beillesztése (a program fókuszba kerüléskor olvassa a vágólapot): XWaylanden a tk vágólap-olvasása
  korlátozott lehet; ha nem megy, a kézi beillesztés (Ctrl+V) marad, és ezt a `LINUX.md` ismert korlátként rögzíti.

A Linuxos próbák egy kézi ellenőrzőlistát kapnak a `LINUX.md`-ben; amíg nem futottak le, a jelentésben `not-run`.

## A buildernek hagyott rész

A modulfelület pontos nevei és szétosztása; hogyan egyszerűsödik a `PY` / `FROZEN` / `BIN_DIR` háromsága úgy, hogy a
meglévő tesztek (`zenelero.PY`, `zenelero.CREATE_NO_WINDOW`) vagy változatlanul menjenek, vagy az importjuk
egyértelműen frissüljön; a `dolphin` keresés és a gyorsítótár-frissítő parancsok (`kbuildsycoca6`, `gtk-update-icon-cache`)
részletei; a `--deps` pontos pacman-csomaglistája (`tk`, `ffmpeg`, `deno`, `python`, esetleg `xdg-utils`).
