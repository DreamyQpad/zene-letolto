# Linux-támogatás – megvalósítási terv

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Zene letöltő Linuxon (Arch, KDE Plasma Wayland) telepíthető, menüből indítható alkalmazás legyen, a Windowsos viselkedés változatlansága mellett.

**Architecture:** A platformfüggő függvények és állandók a `zenelero.py`-ból kis platformmodulokba (`plat_windows.py`, `plat_linux.py`) költöznek, a `plat.py` választja ki a megfelelőt. A Linux-csomag (`.tar.gz` + `install.sh`) a Windowsos gépen épül a `build_linux.py`-val, a Képprofil mintájára. Linuxon a program a telepített venv Pythonjával fut, így a meglévő „nem csomagolt” ág (pip-frissítés, `python -m yt_dlp`) újrahasznosul.

**Tech Stack:** Python 3.13, `unittest`, CustomTkinter, yt-dlp, spotDL, bash (`install.sh`), tarfile.

**Spec:** `docs/superpowers/specs/2026-11-16-linux-tamogatas-design.md`

## Global Constraints

- A Windowsos telepítő és működés **nem változik**; a meglévő 13 teszt és az újak zöldek (`.venv\Scripts\python.exe -m unittest discover -s tests`).
- Egy kódbázis a `main` ágon, **nincs külön Linux-ág**.
- A modul neve **nem** `platform.py` (a standard könyvtárat árnyékolná): `plat.py`, `plat_windows.py`, `plat_linux.py`.
- Linux adatmappa: `$XDG_CONFIG_HOME/zenelero`, ennek hiányában `~/.config/zenelero` (`settings.json`, `history.json`, `archivum/`). Zene alapból `~/Music/Zenelero/`.
- Telepítési helyek: `~/.local/share/zenelero/{app,venv}`, `~/.local/bin/zenelero`, `~/.local/share/applications/zenelero.desktop`, `~/.local/share/icons/hicolor/256x256/apps/zenelero.png`.
- `requirements.txt`: `customtkinter`, `pillow`, `spotdl`, `yt-dlp[default]`.
- Rendszercsomagok: `sudo pacman -S --needed` (`tk`, `ffmpeg`, `deno`), csak `--deps` kapcsolóval.
- Csomag: `out/Zenelero-linux-<verzió>.tar.gz`, benne `zenelero-<verzió>/`; másolat a `Documents\telepitok` mappába.
- Linuxon nincs automatikus heti yt-dlp-frissítés, nincs `--tool` belépő, nincs ablakrejtés; a tesztek nem kerülnek a Linux-csomagba.
- Nyelv: magyar (kommentek, docstringek, üzenetek). A kódba ne kerüljön a fejlesztési folyamat nyoma (jegyszám, „korábban X volt”, `fájl:sor`); a docblock a jelenlegi állapotot és a „miért így”-et írja.
- A commit-üzenetek végére kerül: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Commit és push csak a felhasználó jóváhagyásával: a „Commit” lépések addig csak előkészítik a parancsot. Review-t ne indíts magadtól; a végén egy soros kérdés: „Kérsz review-t erre a diffre?”.

## Review Focus

Amit a spec nem mond ki, de használatkor előjön (a sor végén, melyik feladat tesztje rögzíti):

1. `XDG_CONFIG_HOME` üres, nincs beállítva vagy relatív útvonal → `~/.config/zenelero` (Task 2).
2. Szóközt és ékezetet tartalmazó fájlnév a „Mappa” gombnál → a parancs argumentumlistaként megy, nem shell-szövegként (Task 2).
3. A Leállítás gomb olyan folyamatnál, ami már kilépett, vagy aminek a csoportja már nincs → nincs kivétel (Task 2).
4. `dolphin` / `xdg-open` hiánya, vagy a megnyitandó fájl/mappa nem létezik → nincs kivétel, nem indul semmi (Task 2).
5. Az `install.sh` újrafuttatása nem nyúl a `~/.config/zenelero/` tartalmához, és nem duplikál; a hiányzó rendszercsomag érthető hibával megáll, mielőtt bármit létrehozna (Task 3).

---

## File Structure

| Fájl | Szerep |
|---|---|
| `plat.py` (új) | választó: `win32` → `plat_windows`, különben `plat_linux` |
| `plat_windows.py` (új) | a mai Windowsos viselkedés, a `zenelero.py`-ból átmozgatva |
| `plat_linux.py` (új) | Linuxos megfelelők |
| `zenelero.py` (módosul) | a platformfüggő definíciók helyett `from plat import …`; `VERSION` állandó |
| `requirements.txt`, `assets/icon.png`, `linux/{install.sh,uninstall.sh,zenelero.desktop}` (új) | Linuxos telepítő |
| `build_linux.py` (új) | a Linux-csomag építése Windowson |
| `LINUX.md` (új), `README.md` (módosul) | dokumentáció, kézi ellenőrzőlista |
| `tests/test_plat_windows.py`, `tests/test_plat_linux.py`, `tests/test_plat_contract.py`, `tests/test_linux_scripts.py`, `tests/test_build_linux.py` (új) | tesztek |
| `tests/test_hidden_children.py` (módosul) | `zenelero.CREATE_NO_WINDOW` → `plat.CREATE_NO_WINDOW`; Linuxon kihagyva |

**A `plat_*` modulok közös felülete** (`__all__` mindkettőben pontosan ez, a paraméternevek is egyeznek):

```
FROZEN: bool                 PY: Path                    DATA_DIR: Path          USER_BIN: Path
CREATE_NO_WINDOW: int        FFMPEG_EXE: str             LOG_FONT: str
ytdlp_cmd() -> list[str]     spotdl_cmd() -> list[str]   spotlist_cmd(url) -> list[str]
find_ffmpeg_dir() -> str | None        child_env() -> dict[str, str]
spawn_kwargs() -> dict       kill_tree(proc) -> None     fix_stdio() -> None     hide_child_windows() -> None
reveal(files, folder) -> None            open_folder(path) -> None               set_window_icon(root) -> None
```

---

### Task 1: A Windowsos réteg kiemelése (`plat.py`, `plat_windows.py`)

Tiszta átmozgatás: a viselkedés nem változhat, ezért a tesztek jellemzőtesztek (a mai viselkedést rögzítik).

**Files:**
- Create: `plat.py`, `plat_windows.py`, `tests/test_plat_windows.py`
- Modify: `zenelero.py`, `tests/test_hidden_children.py`

**Interfaces:**
- Produces: a fenti közös felület Windowsos megvalósítása; `plat` ugyanezeket exportálja. `spawn_kwargs()` Windowson `{"creationflags": CREATE_NO_WINDOW}`; `open_folder(path)` = `os.startfile`; `set_window_icon(root)` = a mai `root.after(300, lambda: root.iconbitmap(...))` blokk (ikon: `RES_DIR/"assets"/"icon.ico"`); `FFMPEG_EXE = "ffmpeg.exe"`; `LOG_FONT = "Consolas"`.
- Consumes: —

- [ ] **Step 1: Írd meg a jellemzőteszteket** a `tests/test_plat_windows.py`-ba (`@unittest.skipUnless(sys.platform == "win32", …)` az egész modulra; `import plat, plat_windows`):

```python
def test_spawn_kwargs_ablak_nelkul():        assert plat_windows.spawn_kwargs() == {"creationflags": 0x08000000}
def test_nevek():                             assert (plat_windows.FFMPEG_EXE, plat_windows.LOG_FONT) == ("ffmpeg.exe", "Consolas")
def test_fejlesztoi_eszkozparancsok():       # nem csomagolt futásnál
    assert plat_windows.ytdlp_cmd() == [str(plat_windows.PY), "-m", "yt_dlp"]
    assert plat_windows.spotdl_cmd() == [str(plat_windows.PY), "-m", "spotdl"]
    assert plat_windows.spotlist_cmd("U")[-2:] == [str(HERE / "spotify_list.py"), "U"]   # HERE = a repó gyökere
def test_a_valaszto_windowson_a_windowsos_modult_tolti(): assert plat.spawn_kwargs is plat_windows.spawn_kwargs
def test_kill_tree_taskkill():               # proc = Mock(pid=42), poll() -> None; subprocess.run mockolva
    assert run.call_args.args[0] == ["taskkill", "/PID", "42", "/T", "/F"]
def test_kill_tree_kilepett_folyamatot_nem_bant():  # poll() -> 0 → run nem hívódik
def test_open_folder_startfile():            # os.startfile mockolva → hívva a megadott úttal
def test_reveal_kijeloli_az_elso_letezo_fajlt():   # [nemletezo, tmp fájl] → Popen(f'explorer /select,"{tmp}"')
def test_reveal_mappat_nyit_ha_nincs_fajl():       # [] + létező mappa → os.startfile(mappa)
```

- [ ] **Step 2: Futtasd, hogy lássd elbukni**

Run: `.venv\Scripts\python.exe -m unittest tests.test_plat_windows -v`
Expected: hiba `ModuleNotFoundError: No module named 'plat'`.

- [ ] **Step 3: Hozd létre a `plat_windows.py`-t.** Mozgasd át a `zenelero.py`-ból, szó szerint (docstringekkel együtt): `FROZEN`, `APP_DIR`, `BIN_DIR`, `RES_DIR`, `DATA_DIR`, `USER_BIN`, `PY`, `CREATE_NO_WINDOW`, `ytdlp_cmd`, `spotdl_cmd`, `spotlist_cmd`, `find_ffmpeg_dir`, `child_env`, `kill_tree`, `fix_stdio`, `hide_child_windows`, `reveal`. Add hozzá az új `spawn_kwargs`, `open_folder`, `set_window_icon`, `FFMPEG_EXE`, `LOG_FONT` neveket a fenti felület szerint, és az `__all__`-t a közös felület neveivel. A modul saját `HERE = Path(__file__).resolve().parent`-et használ (a fájl a `zenelero.py` mellett van).

- [ ] **Step 4: Hozd létre a `plat.py`-t**: a docstring egy mondat (a `zenelero.py` ebből veszi a platformfüggő részeket); `if sys.platform == "win32": from plat_windows import *` különben `from plat_linux import *` (mindkettő `# noqa: F401,F403`).

- [ ] **Step 5: Módosítsd a `zenelero.py`-t.**
  - Töröld az átmozgatott definíciókat; maradjon `HERE`, `DEFAULT_OUT`, `SETTINGS_FILE`, `HISTORY_FILE`, `YTDLP_URL`, `YTDLP_API` és minden más; vedd fel: `from plat import (DATA_DIR, FFMPEG_EXE, FROZEN, LOG_FONT, PY, USER_BIN, child_env, find_ffmpeg_dir, fix_stdio, hide_child_windows, kill_tree, open_folder, reveal, set_window_icon, spawn_kwargs, spotdl_cmd, spotlist_cmd, ytdlp_cmd)`.
  - Az öt `creationflags=CREATE_NO_WINDOW` helyére `**spawn_kwargs()` (a `stream`, a `spotify_info`, a `spotdl save`-es tartalék, az előnézet-lekérdezés és a `current_ytdlp_version` hívása).
  - `build_command`: `str(Path(ff) / "ffmpeg.exe")` → `str(Path(ff) / FFMPEG_EXE)`.
  - A `gui()`-ban: az ikonos blokk (`ico = …; root.after(…iconbitmap…)`) → `set_window_icon(root)`; `os.startfile(p)` → `open_folder(p)`; `family="Consolas"` → `family=LOG_FONT`.
  - Töröld a már nem használt importokat (pl. `glob`, `io`, ha tényleg feleslegessé váltak: ellenőrizd `grep`-pel).
  - A `tool_main` változatlanul hívja a `fix_stdio()`-t és a `hide_child_windows()`-t.

- [ ] **Step 6: Igazítsd a `tests/test_hidden_children.py`-t**: `import plat` a `zenelero` import mellé, és `zenelero.CREATE_NO_WINDOW` → `plat.CREATE_NO_WINDOW` (négy helyen). Egyéb változás nincs.

- [ ] **Step 7: Futtasd a teljes tesztcsomagot**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: minden zöld (a korábbi 13 + az új jellemzőtesztek), és `.venv\Scripts\python.exe -c "import zenelero"` hiba nélkül lefut.

- [ ] **Step 8: Commit** (a felhasználó jóváhagyása után): `git add plat.py plat_windows.py zenelero.py tests/ docs/superpowers` → `Platformfüggő rész kiemelése: plat_windows (viselkedés változatlan)`.

---

### Task 2: A Linuxos réteg (`plat_linux.py`) és a közös felület tesztje

**Files:**
- Create: `plat_linux.py`, `tests/test_plat_linux.py`, `tests/test_plat_contract.py`
- Modify: `tests/test_hidden_children.py`

**Interfaces:**
- Consumes: Task 1 közös felülete.
- Produces: `plat_linux` ugyanazzal a felülettel; plusz privát/segéd: `config_dir(environ=os.environ) -> Path` (nem része az `__all__`-nak, a teszt közvetlenül importálja).
- Viselkedés Linuxon: `FROZEN = False`; `PY = Path(sys.executable)`; `DATA_DIR = config_dir()`; `USER_BIN = DATA_DIR / "bin"`; `CREATE_NO_WINDOW = 0`; `FFMPEG_EXE = "ffmpeg"`; `LOG_FONT = "monospace"`; `ytdlp_cmd() = [str(PY), "-m", "yt_dlp"]`, `spotdl_cmd() = [str(PY), "-m", "spotdl"]`, `spotlist_cmd(url) = [str(PY), str(HERE / "spotify_list.py"), url]`; `find_ffmpeg_dir()` = `shutil.which("ffmpeg")` szülőmappája vagy `None`; `child_env()` = `os.environ.copy()`; `spawn_kwargs() = {"start_new_session": True}`; `fix_stdio()` és `hide_child_windows()` nem csinál semmit.
- A modulnak **Windowson is importálhatónak** kell lennie (a tesztek ott futnak): Unix-only nevek (`os.killpg`, `signal.SIGKILL`) csak függvényen belül, `getattr`-ral érhetők el.

- [ ] **Step 1: Írd meg a teszteket** (`tests/test_plat_linux.py`, minden OS-en fut, a külső hívásokat `unittest.mock` helyettesíti):

```python
def test_config_dir_xdg():        assert config_dir({"XDG_CONFIG_HOME": "/x/cfg"}) == Path("/x/cfg") / "zenelero"
def test_config_dir_alapertelmezett():   # üres, hiányzó és relatív érték is
    for env in ({}, {"XDG_CONFIG_HOME": ""}, {"XDG_CONFIG_HOME": "relativ/ut"}):
        assert config_dir(env) == Path.home() / ".config" / "zenelero"
def test_allandok():              assert (FROZEN, CREATE_NO_WINDOW, FFMPEG_EXE, LOG_FONT) == (False, 0, "ffmpeg", "monospace") and PY == Path(sys.executable)
def test_eszkozparancsok():       assert ytdlp_cmd() == [sys.executable, "-m", "yt_dlp"]  # spotdl: "-m", "spotdl"; spotlist: [.., str(HERE/"spotify_list.py"), url]
def test_spawn_kwargs():          assert spawn_kwargs() == {"start_new_session": True}
def test_find_ffmpeg_dir():       # which -> "/usr/bin/ffmpeg" → str(Path("/usr/bin/ffmpeg").parent); which -> None → None
def test_child_env_masolat():     env = child_env(); env["X_PROBA"] = "1"; assert "X_PROBA" not in os.environ
def test_ablakrejtes_nincs():     # hide_child_windows() és fix_stdio() None-t ad, subprocess.Popen.__init__ azonos marad
def test_kill_tree_kilepett_folyamat():   # poll() -> 0 és killpg mockolva (create=True) → killpg egyszer sem hívódik, nincs Timer
def test_kill_tree_term_majd_kill():      # proc=Mock(pid=4242); grace=0.05 → killpg(4242, SIGTERM), majd (esemény-alapú várakozással, max 2 mp) killpg(4242, 9)
def test_kill_tree_eltunt_csoport():      # killpg → ProcessLookupError: egyik hívásnál sem jön kivétel
def test_reveal_dolphin():        # fájl neve "Árvíztűrő tükörfúrógép dal.mp3" (tmp-ben), which("dolphin") van → Popen első argumentuma ["dolphin", "--select", str(fájl)]
def test_reveal_dolphin_nelkul(): # which -> None → ["xdg-open", str(fájl.parent)]
def test_reveal_csak_mappa():     # files=[] + létező mappa → ["xdg-open", str(mappa)]
def test_reveal_semmi_nem_letezik():     # Popen nem hívódik, nincs kivétel
def test_reveal_hianyzo_program():       # Popen → FileNotFoundError: nincs kivétel (open_folder-nél is)
def test_open_folder():           # Popen(["xdg-open", str(path)])
def test_ikon_hianyzo_fajl():     # set_window_icon(Mock root) PNG nélküli RES_DIR-rel: root.after nem hívódik, nincs kivétel
```

`tests/test_plat_contract.py`: `plat_windows.__all__` és `plat_linux.__all__` halmaza egyezik; minden név megvan mindkét modulban; a hívhatóknál az `inspect.signature` paraméternevei egyeznek. A `tests/test_hidden_children.py`-ban a `HideChildWindowsTest` és a `ConsolelessParentTest` kapjon `@unittest.skipUnless(sys.platform == "win32", "Windowsos viselkedés")` dekorátort (az utóbbinak már van más skipUnless-e: vond össze egyetlen feltételre).

- [ ] **Step 2: Futtasd, hogy lássd elbukni**

Run: `.venv\Scripts\python.exe -m unittest tests.test_plat_linux tests.test_plat_contract -v`
Expected: `ModuleNotFoundError: No module named 'plat_linux'`.

- [ ] **Step 3: Írd meg a `plat_linux.py`-t** a fenti viselkedéssel és `__all__`-lal. Megvalósítási döntések:
  - `config_dir`: az `XDG_CONFIG_HOME` csak akkor számít, ha nem üres és `posixpath.isabs`.
  - `kill_tree(proc, grace=3.0)`: ha `proc.poll() is not None`, azonnal térjen vissza; különben `os.killpg(proc.pid, signal.SIGTERM)`, majd egy daemon `threading.Timer(grace, …)` a csoportnak `SIGKILL`-t küld (akkor is, ha a vezérfolyamat közben kilépett, mert a gyerekei élhetnek; ha a csoport már nincs, az `ProcessLookupError`, amit elnyel). `ProcessLookupError` mindkét hívásnál elnyelve. Nem blokkolhat: a GUI szálból hívódik. Az új folyamatcsoport azért van, mert a `spawn_kwargs()` `start_new_session=True`-t ad (a csoport azonosítója = `proc.pid`).
  - `reveal`: az első létező fájlra, ha van `dolphin` (`shutil.which`), `["dolphin", "--select", fájl]`; ha nincs, `xdg-open` a fájl mappájára; fájl nélkül a létező `folder`-re `xdg-open`. Egy privát `_launch(argv)` indít `subprocess.Popen(argv, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)`-tal, az `OSError`-t elnyeli. `open_folder(path)` = `_launch(["xdg-open", str(path)])`.
  - `set_window_icon(root)`: ikon `RES_DIR/"assets"/"icon.png"` (`RES_DIR = HERE`); ha nincs ilyen fájl, nem tesz semmit; különben `root.after(300, …)`, a késleltetett hívás `tkinter.PhotoImage(file=…)`-t készít, `root.iconphoto(True, kép)`, és a képre referenciát tart a `root` egy attribútumán (különben a szemétgyűjtő eldobja).

- [ ] **Step 4: Futtasd a teljes tesztcsomagot**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: minden zöld, a Linuxos és a contract tesztek is.

- [ ] **Step 5: Commit** (jóváhagyással): `git add plat_linux.py tests/` → `Linuxos platformmodul és a közös felület tesztje`.

---

### Task 3: Linuxos telepítő (`requirements.txt`, ikon, `.desktop`, `install.sh`, `uninstall.sh`)

**Files:**
- Create: `requirements.txt`, `assets/icon.png` (az `assets/icon-preview.png` másolata, 256×256), `linux/zenelero.desktop`, `linux/install.sh`, `linux/uninstall.sh`, `tests/test_linux_scripts.py`

**Interfaces:**
- Produces: a csomag szerkezete, amit a `build_linux.py` (Task 4) a tar gyökerébe tesz: `zenelero.py`, `plat*.py`, `spotify_list.py`, `requirements.txt`, `assets/icon.png`, `zenelero.desktop`, `install.sh`, `uninstall.sh`.
- `linux/zenelero.desktop`: `Type=Application`, `Name=Zene letöltő`, `Comment=` rövid magyar leírás, `Exec=@EXEC@`, `Icon=zenelero`, `Terminal=false`, `Categories=AudioVideo;Audio;Network;`.
- `install.sh [--deps]`: `set -euo pipefail`; `SRC` = a script mappája; helyek a Global Constraints szerint (`XDG_DATA_HOME` felülírja a `~/.local/share`-t). Sorrend: (1) függőség-ellenőrzés: `python3`, `python3 -c 'import tkinter'` (hiányában `tk`), `ffmpeg`, `deno`; hiányzónál `--deps` + `pacman` esetén `sudo pacman -S --needed --noconfirm …`, különben a hiányzók nevét és a `pacman`-parancsot kiírja stderr-re, és **még bármi létrehozása előtt** hibakóddal kilép; (2) `$APP` újraírása (`rm -rf`, másolás, az `install.sh`, `uninstall.sh`, `zenelero.desktop` nélkül); (3) `python3 -m venv "$VENV"`, ha még nincs; `"$VENV/bin/pip" install -r "$APP/requirements.txt"`; (4) a `~/.local/bin/zenelero` indítóscript (`exec "$VENV/bin/python" "$APP/zenelero.py" "$@"`, abszolút utakkal, `chmod +x`); (5) `.desktop` az `@EXEC@` → `$BIN/zenelero` cserével, ikon másolása; (6) `update-desktop-database`, `kbuildsycoca6`, `gtk-update-icon-cache`, **csak ha van, és a hibájuk nem állíthatja meg** a telepítést. A `~/.config/zenelero`-hoz soha nem nyúl.
- `uninstall.sh [--purge]`: törli a `$BASE`-t, az indítóscriptet, a `.desktop`-ot, az ikont, és ugyanúgy frissíti a gyorsítótárakat; `--purge` a `config_dir`-t is. Újrafuttatva hibátlan.

- [ ] **Step 1: Írd meg a teszteket** (`tests/test_linux_scripts.py`; kihagyva, ha nincs `bash` a `PATH`-on; a Git Bash megfelel). A teszt egy ideiglenes „csomagmappát” épít a repó fájljaiból (a tar szerkezetével), egy külön mappába **csonkokat** tesz (`python3`, `ffmpeg`, `deno`: bash-scriptek; a `python3 -m venv D` csonk létrehozza a `D/bin/python`-t és a `D/bin/pip`-et, utóbbi az argumentumait a `D/pip.log`-ba írja; `python3 -c …` 0-val tér vissza), és `HOME`-ot ideiglenes mappára állítja, az `XDG_*` változókat törölve. Az utakat bash-formára kell hozni (Windowson `C:\x` → `/c/x`): erre legyen egy `bash_path(p)` segéd. Tesztek:

```python
def test_szintaxis():                 # `bash -n` mindkét scripten rc == 0
def test_telepites_letrehozza_a_fajlokat():
    # rc == 0; létezik: HOME/.local/bin/zenelero (tartalmaz "/venv/bin/python" és "/app/zenelero.py"),
    # HOME/.local/share/applications/zenelero.desktop (Exec= sor == HOME/.local/bin/zenelero, nincs "@EXEC@"),
    # HOME/.local/share/icons/hicolor/256x256/apps/zenelero.png; a pip.log tartalmaz "-r" és "requirements.txt";
    # az app mappában van zenelero.py, nincs install.sh
def test_ujrafuttatas_nem_nyul_a_beallitasokhoz():
    # előre: HOME/.config/zenelero/settings.json = '{"x": 1}'; kétszeri telepítés után rc == 0 és a fájl változatlan
def test_hianyzo_csomag_megall_telepites_elott():
    # ffmpeg nélküli csonkmappával rc != 0, stderr tartalmazza: "ffmpeg" és "pacman"; HOME/.local/bin nem jön létre
def test_eltavolitas():               # a program, parancs, .desktop, ikon eltűnik; a config megmarad; --purge-dzsal a config is
def test_eltavolitas_ketszer():       # másodszori futtatás is rc == 0
```

- [ ] **Step 2: Futtasd, hogy lássd elbukni**

Run: `.venv\Scripts\python.exe -m unittest tests.test_linux_scripts -v`
Expected: hibák: a `linux/install.sh` stb. hiányzik.

- [ ] **Step 3: Hozd létre a fájlokat** a fenti leírás szerint. Az `install.sh`/`uninstall.sh` sortörése LF legyen (`.gitattributes` nem kell: a `build_linux.py` is LF-re cserél, a tesztek `bash`-sel futtatják, ezért a fájlokat LF-fel írd). `requirements.txt` négy sora a Global Constraints szerint. `cp assets/icon-preview.png assets/icon.png`.

- [ ] **Step 4: Futtasd a teszteket**

Run: `.venv\Scripts\python.exe -m unittest tests.test_linux_scripts -v`
Expected: mind zöld (vagy bash nélkül skipped; ezt a jelentésben jelezd).

- [ ] **Step 5: Ellenőrizd a függőséglistát tiszta környezetben.** Készíts a scratchpadben új venvet, telepítsd a `requirements.txt`-et, és futtasd: `python -c "import customtkinter, PIL, yt_dlp, spotdl"`, `python -m pip check` és `python -m spotdl --version`, valamint `python -m yt_dlp --version`. Expected: mind hiba nélkül lefut; ha valami hiányzik, vedd fel a `requirements.txt`-be (és jelezd a jelentésben). Az `yt-dlp-ejs` meglétét `pip show yt-dlp-ejs` igazolja.

- [ ] **Step 6: Commit** (jóváhagyással): `git add requirements.txt assets/icon.png linux/ tests/` → `Linuxos telepítő: install.sh, uninstall.sh, .desktop, requirements`.

---

### Task 4: `build_linux.py`, `VERSION`, dokumentáció

**Files:**
- Create: `build_linux.py`, `LINUX.md`, `tests/test_build_linux.py`
- Modify: `zenelero.py` (`VERSION = "1.0.1"` az állandók közé), `README.md`

**Interfaces:**
- Consumes: Task 3 fájlstruktúrája; `plat_windows.py` kimarad; `plat.py` hivatkozása a `plat_windows`-ra megengedett (`PLATFORM_ONLY = {"plat_windows"}`).
- Produces: `build(out_dir: Path, docs_dir: Path | None = None) -> Path` (a tar elérési útja; ha `docs_dir` meg van adva, oda is másol); `main()` = `build(ROOT / "out", Path.home() / "Documents" / "telepitok")` + két kiírt sor (`Kész: …`, `Másolat: …`); `version() -> str` (a `zenelero.py`-ból, a `^VERSION = "(.+?)"` mintával).
- Tar: `zenelero-<verzió>/` alatt a `ROOT/*.py` fájlok `plat_windows.py` és `build_linux.py` nélkül (a `zenelero.py` mód 0o755, a többi 0o644), `requirements.txt`, `assets/icon.png`, `README.md`, `LINUX.md` (0o644), `install.sh`, `uninstall.sh` (0o755, a `linux/`-ból laposan), `zenelero.desktop` (0o644). A szöveges fájlok CRLF-je LF-re cserélve, a PNG érintetlen. A csomagoló előbb ellenőriz: minden betett `.py` lefordul, nincs a csomagból hiányzó helyi import (a `PLATFORM_ONLY` kivételével), minden adatfájl megvan; hibánál `SystemExit`-tel áll meg, a hibák felsorolásával.

- [ ] **Step 1: Írd meg a teszteket** (`tests/test_build_linux.py`, `build(tmp)`-et hívva):

```python
def test_a_tar_neve_es_gyokere():     # tmp/Zenelero-linux-<VERSION>.tar.gz; minden tag a "zenelero-<VERSION>/" alatt
def test_tartalom():                  # benne: zenelero.py, plat.py, plat_linux.py, spotify_list.py, requirements.txt, assets/icon.png, LINUX.md, install.sh, uninstall.sh, zenelero.desktop
def test_kimarad_a_windowsos_resz():  # nincs: plat_windows.py, build_linux.py, build.ps1, zenelero.bat, tests/*, build_installer/*
def test_modok():                     # install.sh és uninstall.sh 0o755, zenelero.py 0o755, plat.py 0o644
def test_nincs_crlf():                # egyetlen .py/.sh/.md/.desktop/.txt tagban sincs b"\r\n"
def test_masolat_a_docs_mappaba():    # docs_dir megadva → ott is megvan; None → nem készül másolat
def test_version_a_zenelero_pyabol(): # version() == zenelero.VERSION
```

- [ ] **Step 2: Futtasd, hogy lássd elbukni**

Run: `.venv\Scripts\python.exe -m unittest tests.test_build_linux -v`
Expected: `ModuleNotFoundError: No module named 'build_linux'`.

- [ ] **Step 3: Írd meg a `build_linux.py`-t** a fenti felülettel (a `E:\Development\kijelzo\build_linux.py` a minta: `local_imports`-ellenőrzés `ast`-tal, `tarfile`, `TarInfo` módokkal, `uname`/`gname` üres). Vedd fel a `VERSION = "1.0.1"` sort a `zenelero.py`-ba a `YTDLP_API` alá.

- [ ] **Step 4: Írd meg a `LINUX.md`-t** (magyarul, a `E:\Development\kijelzo\LINUX.md` mintájára, tömören): célgép (Arch, KDE Plasma Wayland); telepítés (`tar xzf …; cd zenelero-<verzió>; ./install.sh --deps; zenelero`); fájlhelyek (a Global Constraints szerint); frissítés (Frissítés gomb = pip a venvben, nincs heti automatika); eltávolítás (`uninstall.sh [--purge]`); az XWayland-os kitétel; **kézi ellenőrzőlista**, minden pontnál `[ ] nem futott` állapottal: (1) `./install.sh --deps` végigmegy; (2) a menüben megjelenik, az ikon látszik, a tálcán az ikon a menübejegyzéshez csoportosul; (3) YouTube-szám letöltése; (4) Spotify-album letöltése, nincs felugró ablak; (5) Leállítás gomb: `pgrep -a 'deno|ffmpeg'` üres a leállítás után; (6) Frissítés gomb; (7) „Mappa” gomb Dolphinban kijelöli a fájlt, „Megnyitás” a mappát; (8) vágólap-link automatikus beillesztése (ha nem megy XWaylanden: ismert korlát, marad a Ctrl+V); (9) skálázás és betűk; (10) a spotDL fut az Arch aktuális Pythonján; (11) `install.sh` újrafuttatása nem bántja a beállításokat; (12) `uninstall.sh`. A `README.md`-be kerüljön egy „Linux” szakasz (két-három mondat + hivatkozás a `LINUX.md`-re), és az „Állapot” szakasz mondja ki: a Linuxos változat tesztelése valódi gépen még nem történt meg (amíg a kézi lista le nem futott).

- [ ] **Step 5: Futtasd a teljes tesztcsomagot, majd építsd meg a csomagot**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v` → minden zöld.
Run: `.venv\Scripts\python.exe build_linux.py` → `Kész: …\out\Zenelero-linux-1.0.1.tar.gz` és `Másolat: …`.

- [ ] **Step 6: Commit** (jóváhagyással): `git add build_linux.py LINUX.md README.md zenelero.py tests/` → `Linux-csomag építése (build_linux.py), LINUX.md, VERSION`.

---

### Task 5: Végső ellenőrzés (nincs új kód)

**Files:** nincs; csak futtatás és jelentés.

- [ ] **Step 1: Teljes tesztcsomag**: `.venv\Scripts\python.exe -m unittest discover -s tests -v` → Expected: minden zöld; jegyezd fel a darabszámot és az esetleges `skipped` tesztek okát.

- [ ] **Step 2: A Windowsos telepítő újraépítése és füstpróba.** `powershell -ExecutionPolicy Bypass -File build.ps1` → Expected: `Kesz: …\out\Zene-letolto-telepito.exe`. A `E:\Development\Telepítők\` mappában lévő, felhasználó által kipróbált telepítőt **ne írd felül**. Füstpróba az épített `build_installer\dist\ZeneLetolto\ZeneLetolto.exe`-vel (`Start-Process … -RedirectStandardOutput`): (a) `--tool yt-dlp --version` a kimenetfájlban verziószámot ad (pl. `2026.10.26`); (b) argumentum nélkül indítva 5 mp után a folyamat még fut (a felület feljött), utána állítsd le; (c) `Get-CimInstance Win32_Process` szerint a futás alatt nem indul `cmd.exe`/`conhost.exe` gyerekfolyamat a `ZeneLetolto.exe` alatt.

- [ ] **Step 3: A Linux-csomag ellenőrzése.** Csomagold ki az `out\Zenelero-linux-1.0.1.tar.gz`-t egy új, üres mappába (a scratchpadben), listázd a tartalmát (`tar tzf`), és futtasd a kicsomagolt mappán kívülről: `.venv\Scripts\python.exe -I -c "import sys; sys.path.insert(0, r'<kicsomagolt>'); import plat_linux"` → Expected: hiba nélkül. Futtasd `bash -n install.sh` és `bash -n uninstall.sh` a kicsomagolt példányon.

- [ ] **Step 4: Jelentés magyarul.** Windowsra: mit futtattál és mi lett az eredmény (a tesztek darabszáma, a telepítő füstpróbája). Linuxra: minden, ami a `LINUX.md` kézi listáján áll, `not-run` (mert itt nincs Linux/WSL), a tiszta logika (útvonalak, parancsépítés, `kill_tree` logika, `install.sh` csonkokkal) pedig `verified` a Windowson lefutott tesztek alapján. Zárd egy sorral: „Kérsz review-t erre a diffre?”.
