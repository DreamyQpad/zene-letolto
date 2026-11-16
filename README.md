# Zene letöltő

YouTube / Spotify / SoundCloud (és sok más yt-dlp által ismert oldal) linkjéből **hang vagy videó**. A letöltést a
[yt-dlp](https://github.com/yt-dlp/yt-dlp) és a [spotDL](https://github.com/spotDL/spotify-downloader) végzi, a program egy
CustomTkinter-felület (és parancssor) köréjük.

## Mit tud
- Hang (mp3 / flac / m4a / opus / wav) vagy videó (mp4, választható minőség); lista, album, elemkiválasztó
- Spotify-linkek (spotDL: YouTube Music-ról tölt, Spotify-címkékkel, dalszöveg-beágyazással), SoundCloud, Bandcamp, Mixcloud stb.
- **Sor** (több link külön állapottal), **előzmények**, **előnézet** (cím, borító, hossz), vágólap-link automatikus beillesztése
- Archívum (már letöltöttek kihagyása), hangerő-kiegyenlítés, `.m3u8` lejátszási lista, fejezetvágás, időszakasz-kivágás
- Magyar hibamagyarázatok, automatikus yt-dlp-frissítés hetente (telepített módban), témák
- Kimenet alapból: `Music\Zenelero\Előadó\Album\`

## Futtatás forrásból
```
python -m venv .venv
.venv\Scripts\pip install customtkinter yt-dlp spotdl pillow
.venv\Scripts\python zenelero.py
```
Parancssor: `python zenelero.py <link> [mappa] [--video] [--sort] [--clean] [--archive] [--split] [--norm] [--m3u] [--nolyrics] [--start=1:30] [--end=3:45]`

Kell hozzá az `ffmpeg` (és a yt-dlp néhány oldalához a `deno`) a PATH-on, vagy a program `bin` mappájában.

## Telepítő építése (Windows)
Kell hozzá: PyInstaller a venvben, [Inno Setup 6](https://jrsoftware.org/isinfo.php), és az `ffmpeg.exe` + `deno.exe`
a `build_installer\bin-src\` mappában (ezek nincsenek a repóban, túl nagyok).
```
powershell -ExecutionPolicy Bypass -File build.ps1
```
Eredmény: `out\Zene-letolto-telepito.exe`. Adatok telepített módban: `%APPDATA%\Zene letöltő\`.

## Linux
Arch-alapú rendszerre (KDE Plasma, Wayland) is készült, de valódi gépen még nem lett kipróbálva (lásd Állapot). A terv
szerint a Windowson épített `Zenelero-linux-<verzió>.tar.gz` csomagot (`python build_linux.py`) Linuxon az
`./install.sh --deps` telepíti, a program az alkalmazásmenüből és a `zenelero` paranccsal indítható, az
`./uninstall.sh` távolítja el. Telepítés, fájlhelyek, ismert korlátok és a kézi ellenőrzőlista: [LINUX.md](LINUX.md).

## Állapot
Windows 11-en használatra kész. A Linuxos változat valódi gépen még nem lett tesztelve (a kézi ellenőrzőlista a
[LINUX.md](LINUX.md)-ben van, egyelőre egyik pontja sem futott le). Nem teljesen tesztelt: SoundCloud tényleges letöltés, az automatikus frissítés letöltése
telepített módban, néhány oldal (Audiomack – törött yt-dlp-extractor; Spreaker, Libsyn, Acast, Twitch VOD).
