"""Linuxos platformréteg: útvonalak, eszközparancsok, folyamatkezelés, fájlkezelő és ablakikon.

A közös felületet a plat.py exportálja; a zenelero.py onnan veszi a platformfüggő részeket.
A modul Windowson is importálható (a tesztek ott is futnak): a Unix-only részek függvényen belül élnek."""
import os
import posixpath
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

__all__ = [
    "FROZEN", "PY", "DATA_DIR", "USER_BIN", "CREATE_NO_WINDOW", "FFMPEG_EXE", "LOG_FONT",
    "ytdlp_cmd", "spotdl_cmd", "spotlist_cmd", "find_ffmpeg_dir", "child_env",
    "spawn_kwargs", "kill_tree", "fix_stdio", "hide_child_windows",
    "reveal", "open_folder", "set_window_icon",
]

HERE = Path(__file__).resolve().parent
RES_DIR = HERE                                         # az ikon a forrásmappa assets/ alatt van


def config_dir(environ=os.environ):
    """A beállítások mappája: az XDG_CONFIG_HOME (ha abszolút útvonal), különben ~/.config."""
    base = environ.get("XDG_CONFIG_HOME", "")
    if not base or not posixpath.isabs(base):          # az XDG szerint a relatív érték érvénytelen
        return Path.home() / ".config" / "zenelero"
    return Path(base) / "zenelero"


FROZEN = False                                         # Linuxon nincs csomagolt (PyInstalleres) változat
PY = Path(sys.executable)
DATA_DIR = config_dir()
USER_BIN = DATA_DIR / "bin"
CREATE_NO_WINDOW = 0                                   # Windows-specifikus; itt nincs jelentése
FFMPEG_EXE = "ffmpeg"
LOG_FONT = "monospace"


def ytdlp_cmd():
    return [str(PY), "-m", "yt_dlp"]


def spotdl_cmd():
    return [str(PY), "-m", "spotdl"]


def spotlist_cmd(url):
    return [str(PY), str(HERE / "spotify_list.py"), url]


def find_ffmpeg_dir():
    p = shutil.which("ffmpeg")
    return str(Path(p).parent) if p else None


def child_env():
    return os.environ.copy()


def spawn_kwargs():
    """A gyerekfolyamat-indítások (Popen / run) platformfüggő kiegészítő argumentumai: itt saját
    folyamatcsoport, hogy a kill_tree az egész fát (yt-dlp, ffmpeg, deno) le tudja állítani."""
    return {"start_new_session": True}


def kill_tree(proc, *, grace=3.0):
    """A folyamat és a gyerekei leállítása: azonnal SIGTERM a csoportnak, majd `grace` másodperc múlva SIGKILL.
    Nem blokkol (a GUI szálból hívódik): a SIGKILL-t daemon időzítő küldi, akkor is, ha a vezérfolyamat
    közben kilépett, mert a gyerekei még élhetnek. A csoport azonosítója a proc.pid (start_new_session)."""
    if not proc or proc.poll() is not None:
        return
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    def force_kill():
        try:
            os.killpg(pgid, getattr(signal, "SIGKILL", 9))
        except ProcessLookupError:                     # a csoport már leállt
            pass

    timer = threading.Timer(grace, force_kill)
    timer.daemon = True
    timer.start()


def fix_stdio():
    """Linuxon nincs konzol nélküli exe: a szabványos kimenetek adottak."""


def hide_child_windows():
    """Linuxon a gyerekfolyamatok nem nyitnak konzolablakot."""


def _launch(argv):
    """Leválasztott külső program indítása (fájlkezelő); a hiányzó program nem hiba."""
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def reveal(files, folder):
    """Fájl kijelölése a Fájlkezelőben (Dolphin, ha van), különben a mappa megnyitása."""
    first = next((f for f in files if Path(f).exists()), None)
    if first:
        if shutil.which("dolphin"):
            _launch(["dolphin", "--select", str(first)])
        else:
            _launch(["xdg-open", str(Path(first).parent)])
    elif folder and Path(folder).exists():
        _launch(["xdg-open", str(folder)])


def open_folder(path):
    """Mappa megnyitása a Fájlkezelőben."""
    _launch(["xdg-open", str(path)])


def set_window_icon(root):
    """Az ablak ikonja a forrásmappa assets/icon.png fájljából (ha megvan)."""
    icon = RES_DIR / "assets" / "icon.png"
    if not icon.is_file():
        return

    def apply():
        import tkinter
        image = tkinter.PhotoImage(file=str(icon))
        root.iconphoto(True, image)
        root._app_icon = image                         # referencia nélkül a szemétgyűjtő eldobná a képet

    root.after(300, apply)                             # a customtkinter kb. 200 ms után felülírja az ikont
