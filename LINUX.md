# Zene letöltő – Linux (KDE Plasma Wayland)

Átadó jegyzet: a Linux-rész Windows-gépen készült, valódi Linuxos gépen **még nem lett kipróbálva**. A lenti kézi
ellenőrzőlista minden pontja `[ ] nem futott`, amíg valaki le nem futtatja. Ugyanaz a program, mint a Windowsos
változat, egyetlen kódbázisból (`main` ág, nincs külön Linux-ág).

Célgép: Arch-alapú rendszer (Arch, CachyOS, Garuda), KDE Plasma, Wayland. A felület tk/customtkinter, ezért a terv
szerint XWaylanden fut; ezt a kézi lista ellenőrzi.

## Felépítés
- `zenelero.py` – belépési pont és felület. A platformfüggő részeket a `plat.py` választja (win32 → `plat_windows`,
  különben `plat_linux`).
- `plat_linux.py` – adatmappa, eszközparancsok, `ffmpeg` keresése, gyerekfolyamatok indítása és leállítása
  (`killpg`), mappa megnyitása / fájl kijelölése (`dolphin --select`, különben `xdg-open`), ablak-ikon.
- `spotify_list.py` – a Spotify-lista lekérése (a spotDL-lel együtt fut).
- A Windowsos réteg (`plat_windows.py`), a build- és tesztfájlok nincsenek a csomagban.

## Telepítés a kész csomagból
A csomag Windowson épül ugyanabból a forrásból (`.venv\Scripts\python build_linux.py` → `out\Zenelero-linux-<verzió>.tar.gz`,
másolat a `Documents\telepitok` mappába). Linuxon:
```
tar xzf Zenelero-linux-<verzió>.tar.gz && cd zenelero-<verzió>
./install.sh --deps        # a hiányzó rendszercsomagokat (tk, ffmpeg, deno) is felrakja: sudo pacman -S --needed
zenelero                   # vagy az alkalmazásmenüből: „Zene letöltő"
```
`--deps` nélkül, ha valami hiányzik, az `install.sh` a terve szerint kiírja a hiányzó csomagokat és a `pacman`
parancsot, és még bármi létrehozása előtt megáll. (Csonkolt környezetben, Windowson Git Bash-sel tesztelve; valódi
Linuxon a kézi lista 1. és 11. pontja ellenőrzi.)

## Fájlhelyek
| Mi | Hol |
|---|---|
| program | `~/.local/share/zenelero/app/` |
| virtuális környezet (yt-dlp, spotDL, customtkinter, pillow) | `~/.local/share/zenelero/venv/` |
| indító parancs | `~/.local/bin/zenelero` |
| menübejegyzés | `~/.local/share/applications/zenelero.desktop` |
| ikon | `~/.local/share/icons/hicolor/256x256/apps/zenelero.png` |
| beállítások, előzmények, archívum | `~/.config/zenelero/` (`$XDG_CONFIG_HOME/zenelero`, ha abszolút útvonal) |
| letöltések (alapból) | `~/Music/Zenelero/` |

Az `install.sh` a `XDG_DATA_HOME`-ot figyelembe veszi. Újrafuttatva frissítenie kell (a programot újraírja, a venvben a
csomagokat frissíti), a `~/.config/zenelero/` tartalmához nem nyúl (kézi lista 11.).

## Frissítés (yt-dlp, spotDL)
A **Frissítés** gomb a kód szerint a telepített venvben futtatja a `pip install -U yt-dlp spotdl` parancsot (nem kell
hozzá root); Linuxon még nem próbáltuk (kézi lista 6.). Linuxon nincs automatikus heti ellenőrzés, csak a gomb.
Maga a program frissítése: az új csomaggal `./install.sh`.

## Eltávolítás
```
./uninstall.sh             # program, venv, parancs, menübejegyzés, ikon; a beállítások megmaradnak
./uninstall.sh --purge     # a beállításokat, előzményeket, archívumot is törli
```
A script úgy készült, hogy újrafuttatva (vagy telepítés nélkül) is hibátlanul fusson; csonkolt környezetben tesztelve,
valódi Linuxon a kézi lista 12. pontja ellenőrzi.

## Ismert korlátok
- A felület XWaylanden fut majd (nincs natív Wayland-ablak); a skálázás és a betűk megjelenése ezért eltérhet.
- A vágólap-link automatikus beillesztése (fókuszba kerüléskor) XWaylanden korlátozott lehet; ha nem működik, a kézi
  beillesztés (Ctrl+V) marad.
- Csak Arch-alapú rendszerre (pacman) és KDE-re van megírva; más disztrón a rendszercsomagokat kézzel kell felrakni.
- A scriptek az ismeretlen kapcsolókat nem utasítják el (az `install.sh` csak a `--deps`-et, az `uninstall.sh` csak
  a `--purge`-ot ismeri; minden mást figyelmen kívül hagynak). Ne használd a `--help`-et: nem súgót ad, hanem
  telepít / töröl.
- Nincs `--tool` belépő és ablakrejtés (nincs csomagolt exe); nincs automatikus heti yt-dlp-frissítés.

## Hibaelhárítás
- **Az `install.sh` újrafuttatása `No module named pip` hibával megáll** (feltehetően az Arch Python-főverzió
  frissítése után: a régi venv a már nem létező Pythonra mutat; ez a feltevés nincs Linuxon igazolva). Kerülőút:
  ```
  ./uninstall.sh && ./install.sh
  ```
  A `~/.config/zenelero` beállításai megmaradnak, mert `--purge` nélkül az `uninstall.sh` nem törli őket.
- Hiányzó rendszercsomag: `./install.sh --deps`, vagy kézzel `sudo pacman -S --needed tk ffmpeg deno`.

## Kézi ellenőrzőlista (Linuxos gépen)
Állapot: `[ ] nem futott` – a lista addig nem teljesült, amíg valaki ki nem pipálja, a dátummal és a géppel.

1. [ ] nem futott – `./install.sh --deps` végigmegy (tiszta Arch/KDE gépen).
2. [ ] nem futott – a menüben megjelenik a „Zene letöltő", az ikon látszik, és a tálcán az ikon a menübejegyzéshez csoportosul.
3. [ ] nem futott – YouTube-szám letöltése (hang).
4. [ ] nem futott – Spotify-album letöltése; nincs felugró ablak.
5. [ ] nem futott – a Leállítás gomb után a `pgrep -a 'deno|ffmpeg'` üres.
6. [ ] nem futott – a Frissítés gomb lefut (pip a venvben).
7. [ ] nem futott – a „Mappa" gomb Dolphinban kijelöli a fájlt, a „Megnyitás" a mappát nyitja.
8. [ ] nem futott – a vágólap-link automatikus beillesztése (ha XWaylanden nem megy: ismert korlát, marad a Ctrl+V).
9. [ ] nem futott – skálázás és betűk rendben vannak.
10. [ ] nem futott – a spotDL fut az Arch aktuális Pythonján.
11. [ ] nem futott – az `install.sh` újrafuttatása nem bántja a beállításokat (`~/.config/zenelero`).
12. [ ] nem futott – `uninstall.sh` (és `--purge`) a leírás szerint töröl.

## Tesztek
`python -m unittest discover -s tests` a repó gyökeréből (a külső programokat csonkok helyettesítik; a bash-os
script-tesztek bash nélkül kimaradnak). Ezek a tiszta logikát és a csomag tartalmát bizonyítják, a fenti kézi lista
pontjait **nem**. Linuxon a teljes tesztcsomag futtatása még nem történt meg.
