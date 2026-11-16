"""Windowsos platformréteg: útvonalak, eszközparancsok, folyamatkezelés, fájlkezelő és ablakikon.

A közös felületet a plat.py exportálja; a zenelero.py onnan veszi a platformfüggő részeket."""
import glob
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = [
    "FROZEN", "PY", "DATA_DIR", "USER_BIN", "CREATE_NO_WINDOW", "FFMPEG_EXE", "LOG_FONT",
    "ytdlp_cmd", "spotdl_cmd", "spotlist_cmd", "find_ffmpeg_dir", "child_env",
    "spawn_kwargs", "kill_tree", "fix_stdio", "hide_child_windows",
    "reveal", "open_folder", "set_window_icon",
]

HERE = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, "frozen", False))          # PyInstallerrel csomagolt (telepített) változat
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else HERE
BIN_DIR = APP_DIR / "bin"                              # ffmpeg.exe, deno.exe a telepítőből
RES_DIR = Path(getattr(sys, "_MEIPASS", HERE))         # csomagolt erőforrások (ikon)
DATA_DIR = (Path(os.environ.get("APPDATA", str(Path.home()))) / "Zene letöltő") if FROZEN else HERE
USER_BIN = DATA_DIR / "bin"                            # a Frissítéssel letöltött yt-dlp.exe
PY = HERE / ".venv" / "Scripts" / "python.exe"
CREATE_NO_WINDOW = 0x08000000
FFMPEG_EXE = "ffmpeg.exe"
LOG_FONT = "Consolas"


def ytdlp_cmd():
    if FROZEN:
        user_exe = USER_BIN / "yt-dlp.exe"             # a Frissítéssel letöltött, újabb verzió elsőbbséget élvez
        return [str(user_exe)] if user_exe.is_file() else [sys.executable, "--tool", "yt-dlp"]
    return [str(PY), "-m", "yt_dlp"]


def spotdl_cmd():
    return [sys.executable, "--tool", "spotdl"] if FROZEN else [str(PY), "-m", "spotdl"]


def spotlist_cmd(url):
    return ([sys.executable, "--tool", "spotify-list", url] if FROZEN
            else [str(PY), str(HERE / "spotify_list.py"), url])


def find_ffmpeg_dir():
    if (BIN_DIR / "ffmpeg.exe").is_file():
        return str(BIN_DIR)
    p = shutil.which("ffmpeg")
    if p:
        return str(Path(p).parent)
    pattern = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\bin\ffmpeg.exe")
    hits = glob.glob(pattern, recursive=True)
    return str(Path(hits[0]).parent) if hits else None


def child_env():
    """A deno (yt-dlp JS-futtatója) PATH-ra tétele akkor is, ha az Explorer még a régi PATH-t látja."""
    env = os.environ.copy()
    if (BIN_DIR / "deno.exe").is_file():
        env["PATH"] = str(BIN_DIR) + os.pathsep + env.get("PATH", "")
    elif not shutil.which("deno"):
        hits = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\DenoLand.Deno*\deno.exe"))
        if hits:
            env["PATH"] = str(Path(hits[0]).parent) + os.pathsep + env.get("PATH", "")
    return env


def spawn_kwargs():
    """A gyerekfolyamat-indítások (Popen / run) platformfüggő kiegészítő argumentumai: itt konzolablak nélkül."""
    return {"creationflags": CREATE_NO_WINDOW}


def kill_tree(proc):
    if proc and proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       creationflags=CREATE_NO_WINDOW)


def fix_stdio():
    """Ablakos (konzol nélküli) exe-ben a sys.stdout None; a szülő csöveit az öröklött handle-ökből építjük újra."""
    import ctypes
    import msvcrt
    for name, std_id, mode in (("stdout", -11, os.O_WRONLY), ("stderr", -12, os.O_WRONLY)):
        if getattr(sys, name) is not None:
            continue
        h = ctypes.windll.kernel32.GetStdHandle(std_id)
        if h in (0, -1, None):
            setattr(sys, name, open(os.devnull, "w"))
            continue
        fd = msvcrt.open_osfhandle(h, mode)
        setattr(sys, name, io.TextIOWrapper(os.fdopen(fd, "wb", 0), encoding="utf-8", errors="replace",
                                            line_buffering=True))


def hide_child_windows():
    """Minden ezután indított gyerekfolyamat (deno, ffmpeg, ffprobe, cmd) alapból konzolablak nélkül indul.
    A konzol nélküli exe-nek nincs konzolja, amit a gyerekei örökölhetnének, ezért a spotDL és a yt-dlp
    számonkénti deno/ffmpeg hívásai mind új, látható konzolablakot nyitnának és elvennék a fókuszt.
    Az asyncio és a yt-dlp Popen-je is a subprocess.Popen-ből örököl, így ez az egy pont mindkettőt fedi.
    Az os.system külön eset: a C-s system()-et hívja, a subprocess-t kikerüli. A spotapi importáláskor
    os.system("")-ot futtat (konzolszín-trükk), ami itt minden eszközindításkor új konzolt és Windows Terminal
    ablakot nyitna, ezért az os.system a (már ablak nélküli) subprocessen át fut, az üres parancs pedig nem fut."""
    if sys.platform != "win32" or getattr(subprocess.Popen.__init__, "hides_windows", False):
        return
    original = subprocess.Popen.__init__

    def init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    def system(command):
        if not str(command).strip():
            return 0
        shell = os.environ.get("COMSPEC", "cmd.exe")        # a C system()-mel azonos parancssor: <shell> /c <parancs>
        return subprocess.call(f'"{shell}" /c {command}')

    init.hides_windows = True
    subprocess.Popen.__init__ = init
    os.system = system


def reveal(files, folder):
    """Fájl kijelölése a Fájlkezelőben (ha megvan), különben a mappa megnyitása."""
    try:
        first = next((f for f in files if Path(f).exists()), None)
        if first:
            subprocess.Popen(f'explorer /select,"{first}"')
        elif folder and Path(folder).exists():
            os.startfile(folder)
    except OSError:
        pass


def open_folder(path):
    """Mappa megnyitása a Fájlkezelőben."""
    os.startfile(path)


def set_window_icon(root):
    """Az ablak ikonja a csomagolt erőforrásokból (ha megvan)."""
    ico = RES_DIR / "assets" / "icon.ico"
    if ico.is_file():       # a customtkinter kb. 200 ms után felülírja az ikont, ezért késleltetve állítjuk
        root.after(300, lambda: root.iconbitmap(str(ico)))
