"""Zene letöltő - YouTube / Spotify / SoundCloud link -> hang vagy videó. yt-dlp + spotDL alapon.

Indítás: asztali parancsikon vagy zenelero.bat.
CLI: python zenelero.py <link> [mappa] [--video] [--sort] [--clean] [--archive] [--split] [--norm] [--m3u]
                         [--nolyrics] [--start=1:30] [--end=3:45]
"""
import glob
import hashlib
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, "frozen", False))          # PyInstallerrel csomagolt (telepített) változat
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else HERE
BIN_DIR = APP_DIR / "bin"                              # ffmpeg.exe, deno.exe a telepítőből
RES_DIR = Path(getattr(sys, "_MEIPASS", HERE))         # csomagolt erőforrások (ikon)
DATA_DIR = (Path(os.environ.get("APPDATA", str(Path.home()))) / "Zene letöltő") if FROZEN else HERE
USER_BIN = DATA_DIR / "bin"                            # a Frissítéssel letöltött yt-dlp.exe
PY = HERE / ".venv" / "Scripts" / "python.exe"
DEFAULT_OUT = Path.home() / "Music" / "Zenelero"
SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"
CREATE_NO_WINDOW = 0x08000000
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

AUDIO_FORMATS = ["mp3", "flac", "m4a", "opus", "wav"]
VIDEO_QUALITIES = ["legjobb (max 1080p)", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
TIME_RE = re.compile(r"^\d+(:[0-5]?\d){0,2}(\.\d+)?$")
SUPPORTED_SITES = ("youtube.com", "youtu.be", "soundcloud.com", "spotify.com", "bandcamp.com", "mixcloud.com",
                   "archive.org", "jamendo.com", "audius.co", "twitch.tv", "audiomack.com", "podcasts.apple.com",
                   "spreaker.com", "libsyn.com", "acast.com")
SUPPORTED_RE = re.compile(r"^(https?://([\w-]+\.)*(" + "|".join(re.escape(h) for h in SUPPORTED_SITES) +
                          r")(/\S*)?|spotify:\S+)$", re.I)
ARTIST_DIR = "%(artist,creator,uploader,channel,series|Ismeretlen)s/%(album,playlist_title|Egyéb)s/"
NORM_AF = "-af loudnorm=I=-16:TP=-1.5:LRA=11"          # hangerő-kiegyenlítés (EBU R128)
SEP = "|||"

# Címtisztítás (yt-dlp --replace-in-metadata / --parse-metadata; a megadás sorrendje számít)
CLEAN_ARGS = [
    # "(Official Video)", "[4K Remaster]", "(Lyrics)" ... zárójeles szemét
    "--replace-in-metadata", "title",
    r"(?i)\s*[\(\[][^\)\]]*\b(official|lyrics?|lyric video|audio|video|music video|visuali[sz]er|hd|hq|4k|1080p|remaster(ed)?)\b[^\)\]]*[\)\]]",
    "",
    # "... - Official Video" a cím végén
    "--replace-in-metadata", "title",
    r"(?i)\s*[-–|]\s*(official\s+(music\s+)?(video|audio)|lyrics?( video)?|audio|hd|hq)\s*$",
    "",
    # csatornanévből "VEVO", "- Topic"
    "--replace-in-metadata", "uploader", r"(?i)\s*(vevo|official|- topic)\s*$", "",
    # "Előadó - Cím" -> külön előadó és cím (ha nincs kötőjel, a yt-dlp csak figyelmeztet, azt kiszűrjük)
    "--parse-metadata", r"title:(?P<artist>.+?)\s+[-–]\s+(?P<title>.+)",
]

# Érthető magyar magyarázat a gyakori hibákhoz (a sorrend számít: az első találat nyer)
HINTS = [
    (r"(?i)private video", "Privát videó, bejelentkezés nélkül nem tölthető le."),
    (r"(?i)confirm your age|age[- ]restricted|inappropriate for some users",
     "Korhatáros videó: bejelentkezés kellene hozzá."),
    (r"(?i)not a bot", "A YouTube botnak nézte a letöltést. Nyomj Frissítést, majd próbáld újra később."),
    (r"(?i)unavailable|this video is not available|has been removed|no longer available|"
     r"blocked it in your country|not made this video available in your country|copyright",
     "A videó nem elérhető (törölték, vagy az országodban le van tiltva)."),
    (r"(?i)HTTP Error 403|HTTP Error 429|too many requests",
     "A szerver blokkolta a kérést. Nyomj Frissítést, majd próbáld újra egy kis idő múlva."),
    (r"(?i)unsupported url", "Ez a link nem támogatott."),
    (r"(?i)requested format is not available", "Ez a minőség/formátum nem elérhető ehhez a videóhoz: válassz másikat."),
    (r"(?i)getaddrinfo failed|unable to download webpage|timed out|connection (reset|aborted|refused)|"
     r"network is unreachable|name resolution|urlopen error", "Nincs internetkapcsolat, vagy a szerver nem válaszol."),
    (r"(?i)premieres in|live event will begin|this live event", "Az élő közvetítés vagy premier még nem indult el."),
    (r"(?i)not currently live|is offline|currently offline|is_live",
     "Élő adás: ezt nem rögzítem (vég nélküli felvétel lenne). Várd meg, amíg kész lesz a felvétele."),
    (r"(?i)is not a valid url|incomplete youtube id", "Hibás link. Ellenőrizd, hogy a teljes linket másoltad-e ki."),
    (r"(?i)ffmpeg.*not found|ffprobe and ffmpeg not found", "Hiányzik az ffmpeg: telepítsd újra a programot."),
    (r"(?i)no results found|lookuperror", "Ehhez a Spotify-számhoz nem találtam letölthető YouTube-egyezést."),
    (r"(?i)sign in|login required|members-only|join this channel", "Bejelentkezés vagy csatornatagság kell a videóhoz."),
    (r"(?i)failed to parse json|unable to extract|extractor error|please report this issue",
     "A yt-dlp nem boldogul ezzel az oldallal (valószínűleg megváltozott az oldal felépítése). "
     "Nyomj Frissítést, majd próbáld újra."),
]


def hint_for(text):
    for rx, msg in HINTS:
        if re.search(rx, text):
            return msg
    return None


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


def is_spotify(url):
    return "spotify.com" in url or url.startswith("spotify:")


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


def default_opts(**kw):
    o = {"kind": "audio", "fmt": "mp3", "organize": False, "clean": False, "archive": False,
         "split": False, "start": "", "end": "", "items": None,
         "normalize": False, "m3u": False, "lyrics": True}
    o.update(kw)
    return o


def section_arg(o):
    s, e = o["start"].strip(), o["end"].strip()
    if not s and not e:
        return None
    return f"*{s or '0'}-{e or 'inf'}"


def archive_path(out, kind, fmt):
    """A letöltési archívum a program adatmappájában van (nem a zenemappában), kimeneti mappánként és
    formátumonként külön fájlban. A régi, zenemappában lévő .zenelero-archivum-*.txt-t átemeli és törli."""
    key = re.sub(r"\W+", "_", f"{kind}-{fmt}")
    tag = hashlib.sha1(str(out.resolve()).lower().encode("utf-8")).hexdigest()[:8]
    new = DATA_DIR / "archivum" / f"{tag}-{key}.txt"
    old = out / f".zenelero-archivum-{key}.txt"
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        if old.is_file():
            have = set(new.read_text(encoding="utf-8").splitlines()) if new.is_file() else set()
            extra = [l for l in old.read_text(encoding="utf-8").splitlines() if l.strip() and l not in have]
            if extra:
                with open(new, "a", encoding="utf-8") as f:
                    f.write("\n".join(extra) + "\n")
            old.unlink()
    except OSError:
        pass
    return new


def build_command(url, out, o, listfile=None):
    ff = find_ffmpeg_dir()
    kind, fmt = o["kind"], o["fmt"]
    if is_spotify(url):
        tmpl = ("{album-artist}/{album}/{track-number} - {title}.{output-ext}" if o["organize"]
                else "{artists} - {title}.{output-ext}")
        queries = o["items"] or [url]          # kiválasztásnál a szám-URL-ek
        cmd = [*spotdl_cmd(), "download", *queries, "--output", str(out / tmpl), "--format", fmt]
        if ff:
            cmd += ["--ffmpeg", str(Path(ff) / "ffmpeg.exe")]
        cmd += ["--lyrics", "synced", "genius", "musixmatch"] if o["lyrics"] else ["--lyrics"]
        if o["normalize"]:
            cmd += ["--ffmpeg-args", NORM_AF]
        if o["archive"]:
            cmd += ["--archive", str(archive_path(out, "audio", fmt))]
        if o["m3u"] and not o["items"] and ("/playlist/" in url or "/album/" in url):
            cmd += ["--m3u", str(out / "{list[0]}.m3u8")]
        return cmd

    sect = section_arg(o)
    prefix = ARTIST_DIR if (o["organize"] and kind == "audio") else ""
    # --match-filter !is_live: élő adást (pl. Twitch-csatorna) nem rögzítünk, mert vég nélküli felvétel lenne
    cmd = [*ytdlp_cmd(), "--yes-playlist", "--embed-metadata", "--match-filter", "!is_live"]
    if ff:
        cmd += ["--ffmpeg-location", ff]
    if o["items"]:
        cmd += ["--playlist-items", ",".join(str(i) for i in o["items"])]
    if o["archive"] and not sect:              # szakaszkivágásnál az archívum útban lenne (ugyanaz a videó többször)
        cmd += ["--download-archive", str(archive_path(out, kind, fmt))]
    if o["clean"]:
        cmd += CLEAN_ARGS
    if sect:
        cmd += ["--download-sections", sect, "--force-keyframes-at-cuts"]
    if o["split"]:
        cmd += ["--split-chapters", "-o",
                "chapter:" + str(out / (prefix + "%(title)s/%(section_number)02d - %(section_title)s.%(ext)s"))]
    if listfile:    # a kész fájlok listája: sorszám|||lista neve|||útvonal|||cím
        cmd += ["--print-to-file",
                f"after_move:%(playlist_index|)s{SEP}%(playlist_title|)s{SEP}%(filepath)s{SEP}%(title)s", listfile]

    if kind == "video":
        h = fmt.split("p")[0]
        sort = "vcodec:h264,res,acodec:m4a" if not h.isdigit() else f"res:{h},vcodec:h264,acodec:m4a"
        cmd += ["-S", sort, "--merge-output-format", "mp4"]
    else:
        cmd += ["-x", "--audio-format", fmt, "--audio-quality", "0", "--embed-thumbnail",
                # album: a szám albuma, ennek hiányában a lejátszási lista neve; a leírás ne kerüljön a címkékbe
                "--parse-metadata", "%(album,playlist_title|)s:%(meta_album)s",
                "--parse-metadata", ":(?P<meta_description>)",
                "--parse-metadata", ":(?P<meta_synopsis>)"]
        if o["normalize"]:
            cmd += ["--postprocessor-args", "ExtractAudio:" + NORM_AF]
    cmd += ["-o", str(out / (prefix + "%(title)s.%(ext)s")), url]
    return cmd


def kill_tree(proc):
    if proc and proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       creationflags=CREATE_NO_WINDOW)


def stream(cmd, log, holder=None):
    """Parancs futtatása, a kimenetet soronként a log-nak adja. holder: {"proc":..., "cancel":bool}."""
    holder = holder if holder is not None else {}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
                            env=child_env())
    holder["proc"] = proc
    if holder.get("cancel"):               # a megszakítás épp az indulás előtt érkezett
        kill_tree(proc)
    for line in proc.stdout:
        log(line)
    code = proc.wait()
    holder["proc"] = None
    return code


PCT_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
ITEM_RE = re.compile(r"\[download\] Downloading item (\d+) of (\d+)")
DEST_RE = re.compile(r"\[(?:download|ExtractAudio|Merger)\] (?:Destination|Merging formats into):? \"?(.+?)\"?$")
SP_FOUND_RE = re.compile(r"Found (\d+) songs? in")
SP_DONE_RE = re.compile(r'^Downloaded "(.+?)(?:"|$)')   # hosszú cím esetén a konzol kettétöri a sort


def safe_name(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .") or "lista"


def write_m3u(out, entries):
    """entries: [(sorszám, lista neve, útvonal, cím)] -> egy .m3u8 listánként (csak 2+ elemű, létező fájlokból)."""
    groups = {}
    for idx, plist, path, title in entries:
        if plist and idx.isdigit() and Path(path).is_file():
            groups.setdefault(plist, []).append((int(idx), path, title))
    made = []
    for plist, items in groups.items():
        if len(items) < 2:
            continue
        lines = ["#EXTM3U"]
        for _, path, title in sorted(items):
            try:
                rel = os.path.relpath(path, out)
            except ValueError:
                rel = path
            lines += [f"#EXTINF:-1,{title}", rel]
        target = out / f"{safe_name(plist)}.m3u8"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        made.append(target)
    return made


def relativize_m3u(out, since):
    """A spotDL abszolút útvonalakat ír az .m3u8-ba; ezeket relatívra írjuk át (mappa mozgatása után is jó)."""
    for f in out.glob("*.m3u8"):
        try:
            if f.stat().st_mtime < since:
                continue
            lines = f.read_text(encoding="utf-8").splitlines()
            new = []
            for l in lines:
                if l and not l.startswith("#") and os.path.isabs(l):
                    try:
                        l = os.path.relpath(l, out)
                    except ValueError:
                        pass
                new.append(l)
            f.write_text("\n".join(new) + "\n", encoding="utf-8")
        except OSError:
            pass


def run(url, out, o, log, holder=None, ev=None):
    """Egy link letöltése. ev(kind, value): "pct" (0..1), "count" ((i, n)), "label" (szöveg).
    Visszatér: {"code", "files", "folder", "error", "skipped"}."""
    holder = holder if holder is not None else {}
    ev = ev or (lambda *a: None)
    o = dict(o)
    out.mkdir(parents=True, exist_ok=True)
    res = {"code": 0, "files": [], "folder": str(out), "error": "", "skipped": 0}
    log(f"> {url}\n")
    if is_spotify(url):
        if o["kind"] == "video":
            log("A Spotify-ból csak hang tölthető le, ezt hangként (mp3) töltöm.\n")
            o.update(kind="audio", fmt="mp3")
        if o["start"] or o["end"] or o["split"]:
            log("Szakaszkivágás és fejezetvágás Spotify-nál nem működik, ezeket kihagyom.\n")
            o.update(start="", end="", split=False)
    else:
        for name in ("start", "end"):
            if o[name].strip() and not TIME_RE.match(o[name].strip()):
                msg = f"A(z) '{o[name]}' nem érvényes időpont (példa: 1:30 vagy 0:03:15)."
                log(f"HIBA: {msg}\n\n")
                res.update(code=2, error=msg)
                return res

    listfile = None
    if not is_spotify(url):
        fd, listfile = tempfile.mkstemp(suffix=".txt", prefix="zenelero-")
        os.close(fd)
    started = time.time()
    sp = {"total": 0, "done": 0}
    skipped, hints, live = [], [], []

    def filt(line):
        s = line.rstrip("\r\n")
        if s.startswith("[MetadataParser] Could not interpret"):
            return                           # cím-szétszedésnél ez normális, ha nincs benne kötőjel
        m = PCT_RE.match(s)
        if m:
            ev("pct", float(m.group(1)) / 100)
            if float(m.group(1)) < 100:
                return                       # a közbülső százalékokat nem írjuk a naplóba
        m = ITEM_RE.search(s)
        if m:
            ev("count", (int(m.group(1)), int(m.group(2))))
        m = DEST_RE.match(s)
        if m:
            ev("label", Path(m.group(1)).stem)
        m = SP_FOUND_RE.search(s)
        if m:
            sp["total"] = int(m.group(1))
        m = SP_DONE_RE.match(s)
        if m:
            sp["done"] += 1
            ev("label", m.group(1))
            if sp["total"]:
                ev("count", (sp["done"], sp["total"]))
                ev("pct", sp["done"] / sp["total"])
        if "has already been recorded in the archive" in s:
            skipped.append(s)
        if "does not pass filter" in s and "is_live" in s:
            live.append(s)
        log(line)
        if s.startswith("ERROR") or "Error" in s or "LookupError" in s:
            h = hint_for(s)
            if h and h not in hints:
                hints.append(h)
                log(f"  → {h}\n")

    code = stream(build_command(url, out, o, listfile), filt, holder)

    entries = []
    if listfile:
        try:
            for l in Path(listfile).read_text(encoding="utf-8", errors="replace").splitlines():
                parts = l.split(SEP)
                if len(parts) == 4:
                    entries.append(tuple(p.strip() for p in parts))
        except OSError:
            pass
        finally:
            try:
                os.unlink(listfile)
            except OSError:
                pass
    res["files"] = [e[2] for e in entries if Path(e[2]).is_file()]

    if o["split"]:
        # a fejezetekre vágott fájl eredetijét töröljük (a darabok a mellette lévő, azonos nevű mappában vannak)
        for e in entries:
            pp = Path(e[2])
            d = pp.with_suffix("")
            try:
                if pp.is_file() and d.is_dir() and any(d.iterdir()):
                    pp.unlink()
                    log(f"Fejezetekre vágva: {d}\n")
                    res["files"] = sorted(str(x) for x in d.iterdir() if x.is_file())
                    res["folder"] = str(d)
            except OSError:
                pass

    if o["m3u"] and o["kind"] == "audio":
        try:
            if is_spotify(url):
                relativize_m3u(out, started - 2)
            else:
                for target in write_m3u(out, entries):
                    log(f"Lejátszási lista: {target.name}\n")
        except OSError as e:
            log(f"A lejátszási lista fájl nem készült el: {e}\n")

    res["skipped"] = len(skipped)
    res["error"] = hints[0] if hints else ""
    if live and not res["files"]:
        msg = "Élő adás: ezt nem rögzítem (vég nélküli felvétel lenne). Várd meg, amíg kész lesz a felvétele."
        log(f"  → {msg}\n")
        res["error"] = msg
        code = code or 1
    if holder.get("cancel"):
        log("Megszakítva.\n\n")
        res["code"] = 130
        return res
    if skipped:
        log(f"({len(skipped)} elem kihagyva: már letöltötted. Az újratöltéshez kapcsold ki a "
            f"'Már letöltöttek kihagyása' opciót.)\n")
    log("Kész.\n\n" if code == 0 else f"HIBA (kilépési kód: {code})\n\n")
    res["code"] = code
    return res


# ---------------------------------------------------------------- lista / előnézet lekérdezés

def _http_bytes(url, timeout=10):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def spotify_info(url):
    """-> {"kind","name","cover","songs":[{"url","artist","name","duration"}]}"""
    try:    # gyors út: csak a Spotify-adatok, YouTube-keresés nélkül
        r = subprocess.run(spotlist_cmd(url), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=child_env(), creationflags=CREATE_NO_WINDOW, timeout=120)
        line = next(l for l in r.stdout.splitlines() if l.startswith("JSON:"))
        data = json.loads(line[5:])
        return data if isinstance(data, dict) else {"kind": "list", "name": None, "cover": None, "songs": data}
    except Exception:
        pass    # tartalék: spotdl save (lassabb, mert minden számhoz YouTube-egyezést is keres)
    fd, tmp = tempfile.mkstemp(suffix=".spotdl", prefix="zenelero-")
    os.close(fd)
    try:
        subprocess.run([*spotdl_cmd(), "save", url, "--save-file", tmp], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=child_env(),
                       creationflags=CREATE_NO_WINDOW, timeout=240)
        data = json.loads(Path(tmp).read_text(encoding="utf-8"))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    songs = [{"url": s["url"], "artist": s.get("artist") or ", ".join(s.get("artists") or []),
              "name": s["name"], "duration": s.get("duration")} for s in data]
    return {"kind": "list", "name": None, "cover": (data[0].get("cover_url") if data else None), "songs": songs}


def fetch_preview(url):
    """Előnézet + a lista elemei: {"url","title","sub","thumb"(bytes|None),"entries":[(azonosító, cím, hossz_mp)]}.
    Hiba esetén RuntimeError(magyarázat)."""
    thumb_url = None
    chapters = 0
    if is_spotify(url):
        info = spotify_info(url)
        songs = info.get("songs") or []
        if not songs:
            raise RuntimeError("Nem sikerült lekérdezni a Spotify-linket.")
        entries = [(s["url"], f'{s["artist"]} - {s["name"]}', s.get("duration")) for s in songs]
        if info.get("kind") == "track" or len(songs) == 1:
            title = songs[0]["name"]
            sub = f'{songs[0]["artist"]} · Spotify' + (f' · {fmt_dur(songs[0].get("duration"))}'
                                                        if songs[0].get("duration") else "")
        else:
            title = info.get("name") or "Spotify lista"
            sub = f"Spotify · {len(songs)} szám"
        thumb_url = info.get("cover")
    else:
        r = subprocess.run([*ytdlp_cmd(), "-J", "--flat-playlist", "--yes-playlist", url], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=child_env(),
                           creationflags=CREATE_NO_WINDOW, timeout=240)
        try:
            data = json.loads(r.stdout)
        except ValueError:
            data = None
        if not isinstance(data, dict):      # hiba vagy üres válasz (pl. nem élő Twitch-csatorna, hibás link)
            err = next((l for l in r.stderr.splitlines() if l.startswith("ERROR")), r.stderr.strip()[-200:])
            raise RuntimeError(hint_for(r.stderr) or err or "Az oldal nem adott vissza használható adatot.")
        if data.get("_type") == "playlist":
            ents = [e for e in (data.get("entries") or []) if e]
            entries = [(i, e.get("title") or e.get("id") or "?", e.get("duration"))
                       for i, e in enumerate(data.get("entries") or [], 1) if e]
            title = data.get("title") or "Lejátszási lista"
            who = data.get("uploader") or data.get("channel") or ""
            sub = f"Lejátszási lista · {len(entries)} elem" + (f" · {who}" if who else "")
            th = data.get("thumbnails") or (ents[0].get("thumbnails") if ents else None) or []
            thumb_url = th[-1].get("url") if th else None
            if not thumb_url and ents and ents[0].get("id") and "youtube" in (data.get("extractor") or ""):
                thumb_url = f"https://i.ytimg.com/vi/{ents[0]['id']}/mqdefault.jpg"
        else:
            entries = [(1, data.get("title") or url, data.get("duration"))]
            title = data.get("title") or url
            who = data.get("uploader") or data.get("channel") or ""
            d = fmt_dur(data.get("duration"))
            sub = " · ".join(x for x in (who, d) if x)
            thumb_url = data.get("thumbnail")
            chapters = len(data.get("chapters") or [])
    thumb = None
    if thumb_url:
        try:
            thumb = _http_bytes(thumb_url)
        except Exception:
            thumb = None
    return {"url": url, "title": title, "sub": sub, "thumb": thumb, "entries": entries, "chapters": chapters}


def fetch_entries(url):
    return fetch_preview(url)["entries"]


# ---------------------------------------------------------------- frissítés

def bundled_ytdlp_version():
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return "0"


def current_ytdlp_version():
    exe = USER_BIN / "yt-dlp.exe"
    if FROZEN and exe.is_file():
        try:
            r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, env=child_env(),
                               creationflags=CREATE_NO_WINDOW, timeout=90)
            if r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    return bundled_ytdlp_version()


def latest_ytdlp_version():
    import urllib.request
    req = urllib.request.Request(YTDLP_API, headers={"User-Agent": "zene-letolto"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["tag_name"]


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def update_ytdlp_frozen():
    """Telepített változatban a Frissítés a legújabb yt-dlp.exe-t tölti le a felhasználói mappába."""
    import urllib.request
    USER_BIN.mkdir(parents=True, exist_ok=True)
    tmp = USER_BIN / "yt-dlp.exe.new"
    urllib.request.urlretrieve(YTDLP_URL, tmp)
    os.replace(tmp, USER_BIN / "yt-dlp.exe")


def fmt_dur(sec):
    if not sec:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def cli():
    argv = sys.argv[1:]
    flags = {a for a in argv if a.startswith("--") and "=" not in a}
    kv = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    args = [a for a in argv if not a.startswith("--")]
    video = "--video" in flags
    o = default_opts(kind="video" if video else "audio", fmt="legjobb" if video else "mp3",
                     organize="--sort" in flags, clean="--clean" in flags, archive="--archive" in flags,
                     split="--split" in flags, normalize="--norm" in flags, m3u="--m3u" in flags,
                     lyrics="--nolyrics" not in flags, start=kv.get("start", ""), end=kv.get("end", ""))
    out = Path(args[1]) if len(args) > 1 else DEFAULT_OUT
    res = run(args[0], out, o, (lambda s: print(s, end="")) if sys.stdout else (lambda s: None))
    sys.exit(res["code"])


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


def tool_main(name, rest):
    """Csomagolt exe többfunkciós belépője: a yt-dlp / spotDL / Spotify-listázó ugyanabból a csomagból fut."""
    fix_stdio()
    if name == "yt-dlp":
        import yt_dlp
        yt_dlp.main(rest)
    elif name == "spotdl":
        from spotdl.console import console_entry_point
        sys.argv = ["spotdl"] + rest
        console_entry_point()
    elif name == "spotify-list":
        sys.argv = ["spotify_list"] + rest
        import spotify_list  # noqa: F401  (az import futtatja)
    else:
        sys.exit(f"ismeretlen eszköz: {name}")


# ---------------------------------------------------------------- ablak

APPEARANCE = {"Rendszer": "system", "Világos": "light", "Sötét": "dark"}
ACCENTS = {"Kék": "blue", "Zöld": "green", "Sötétkék": "dark-blue"}
DEFAULT_SETTINGS = {"appearance": "Rendszer", "accent": "Kék", "out": str(DEFAULT_OUT),
                    "kind": "Hang", "afmt": "mp3", "vfmt": VIDEO_QUALITIES[0],
                    "sort": True, "clean": True, "archive": True, "split": False,
                    "normalize": False, "m3u": True, "lyrics": True, "autoupdate": True, "clip": True,
                    "last_check": ""}
STATUS_TXT = {"wait": "Vár", "run": "Tölt", "done": "Kész", "err": "Hiba", "skip": "Kihagyva", "cancel": "Leállítva"}
STATUS_COL = {"wait": ("gray40", "gray60"), "run": ("#1f6aa5", "#5aa9e6"), "done": ("#2e8b57", "#4cc38a"),
              "err": ("#c0392b", "#ff6b5e"), "skip": ("gray40", "gray60"), "cancel": ("#b9770e", "#e0a030")}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
        s.update(saved)
        old_fmt = saved.get("fmt")          # régi mentés: egyetlen "fmt" volt, a Hang/Videó váltás nullázta
        if "afmt" not in saved and old_fmt in AUDIO_FORMATS:
            s["afmt"] = old_fmt
        if "vfmt" not in saved and old_fmt in VIDEO_QUALITIES:
            s["vfmt"] = old_fmt
    except Exception:
        pass
    if s["appearance"] not in APPEARANCE:
        s["appearance"] = DEFAULT_SETTINGS["appearance"]
    if s["accent"] not in ACCENTS:
        s["accent"] = DEFAULT_SETTINGS["accent"]
    if s["kind"] not in ("Hang", "Videó"):
        s["kind"] = "Hang"
    if s["afmt"] not in AUDIO_FORMATS:
        s["afmt"] = AUDIO_FORMATS[0]
    if s["vfmt"] not in VIDEO_QUALITIES:
        s["vfmt"] = VIDEO_QUALITIES[0]
    return s


def save_settings(s):
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_history():
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(h):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(h[:200], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


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


def gui():
    import customtkinter as ctk
    from tkinter import filedialog

    S = load_settings()
    q = queue.Queue()
    log_buf = []                 # a napló tartalma, hogy témaváltáskor (újraépítés) ne vesszen el
    lock = threading.Lock()
    st = {"worker": False, "proc": None, "cancel": False, "sel": None, "fetching": False,
          "queue": [], "next_id": 1, "cur": None, "hist": load_history(),
          "preview": None, "prev_state": "none", "prev_url": "", "prev_seq": 0, "prev_msg": "", "prev_job": None,
          "clip_t": 0.0, "last_clip": ""}
    w = {}                       # az aktuális widgetek
    st.update(opt_sig=None, cut=("", ""))
    GREY = dict(fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"), text_color=("gray10", "gray90"))
    MUTED = ("gray40", "gray60")
    URL_RE = re.compile(r"(?i)^(https?://|spotify:)")

    ctk.set_appearance_mode(APPEARANCE[S["appearance"]])
    ctk.set_default_color_theme(ACCENTS[S["accent"]])
    root = ctk.CTk()
    root.title("Zene letöltő")
    root.geometry("920x940")
    root.minsize(800, 780)
    ico = RES_DIR / "assets" / "icon.ico"
    if ico.is_file():       # a customtkinter kb. 200 ms után felülírja az ikont, ezért késleltetve állítjuk
        root.after(300, lambda: root.iconbitmap(str(ico)))

    def set_s(key, value):
        S[key] = value
        save_settings(S)

    def on_kind(v):
        set_s("kind", v)
        render_options(force=True)

    def on_fmt(v):
        set_s("afmt" if v in AUDIO_FORMATS else "vfmt", v)

    def on_appearance(v):
        set_s("appearance", v)
        ctk.set_appearance_mode(APPEARANCE[v])

    def on_accent(v):
        set_s("accent", v)
        ctk.set_default_color_theme(ACCENTS[v])
        build()
        root.after(80, open_settings)       # az újraépítés a beállítások ablakot is bezárta

    def check(parent, key, text):
        cb_ = ctk.CTkCheckBox(parent, text=text, command=lambda: set_s(key, bool(cb_.get())))
        if S[key]:
            cb_.select()
        return cb_

    # ---- beállítások ablak (ritkán használt dolgok)
    def open_settings():
        try:
            if w.get("settings") is not None and w["settings"].winfo_exists():
                w["settings"].lift()
                return
        except Exception:
            pass
        top = ctk.CTkToplevel(root)
        w["settings"] = top
        top.title("Beállítások")
        top.geometry("470x430")
        top.transient(root)
        bold = ctk.CTkFont(weight="bold")

        def section(text, first=False):
            ctk.CTkLabel(top, text=text, font=bold).pack(anchor="w", padx=22, pady=(18 if first else 20, 6))

        section("Megjelenés", True)
        r1 = ctk.CTkFrame(top, fg_color="transparent")
        r1.pack(fill="x", padx=22)
        ctk.CTkLabel(r1, text="Téma:", width=110, anchor="w").pack(side="left")
        ap = ctk.CTkSegmentedButton(r1, values=list(APPEARANCE), command=on_appearance)
        ap.set(S["appearance"])
        ap.pack(side="left")
        r2 = ctk.CTkFrame(top, fg_color="transparent")
        r2.pack(fill="x", padx=22, pady=(10, 0))
        ctk.CTkLabel(r2, text="Színkiemelés:", width=110, anchor="w").pack(side="left")
        ac = ctk.CTkOptionMenu(r2, values=list(ACCENTS), width=130, command=on_accent)
        ac.set(S["accent"])
        ac.pack(side="left")

        section("Működés")
        check(top, "clip", "Link beillesztése a vágólapról, ha az ablakra visszalépek").pack(anchor="w", padx=22)
        check(top, "autoupdate", "A yt-dlp automatikus frissítése (hetente, a háttérben)").pack(
            anchor="w", padx=22, pady=(10, 0))

        section("Karbantartás")
        r3 = ctk.CTkFrame(top, fg_color="transparent")
        r3.pack(fill="x", padx=22)
        ctk.CTkButton(r3, text="yt-dlp frissítése most", width=170, command=lambda: (top.destroy(), update_tools())
                      ).pack(side="left")
        w["ver"] = ctk.CTkLabel(r3, text="verzió: …", text_color=MUTED)
        w["ver"].pack(side="left", padx=14)
        ctk.CTkLabel(top, text="A YouTube-hibák nagy részét a frissítés javítja.", text_color=MUTED,
                     anchor="w").pack(anchor="w", padx=22, pady=(8, 0))
        threading.Thread(target=lambda: q.put(("ver", current_ytdlp_version())), daemon=True).start()

        ctk.CTkButton(top, text="Kész", width=100, command=top.destroy).pack(side="bottom", anchor="e", padx=22,
                                                                              pady=18)

    def browse():
        d = filedialog.askdirectory(initialdir=w["out"].get() or str(DEFAULT_OUT))
        if d:
            w["out"].delete(0, "end")
            w["out"].insert(0, str(Path(d)))
            set_s("out", str(Path(d)))

    def open_folder():
        p = Path(w["out"].get() or DEFAULT_OUT)
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(p)

    def log_write(s):
        log_buf.append(s)
        del log_buf[:-3000]
        box = w.get("log")
        if box is None:
            return
        box.configure(state="normal")
        box.insert("end", s)
        box.see("end")
        box.configure(state="disabled")

    # ---- előnézet kártya
    def render_preview():
        f = w["prev"]
        for c in f.winfo_children():
            c.destroy()
        w["pick"] = None
        state, pv = st["prev_state"], st["preview"]
        if state == "none":
            f.pack_forget()
            render_options()
            return
        f.pack(fill="x", padx=16, pady=(0, 14))
        if state == "loading":
            ctk.CTkLabel(f, text="Adatok lekérése…", text_color=("gray40", "gray60")).pack(anchor="w")
        elif state == "err":
            ctk.CTkLabel(f, text="Nem tölthető le: " + st["prev_msg"], text_color=STATUS_COL["err"],
                         wraplength=760, justify="left").pack(anchor="w")
        else:
            row = ctk.CTkFrame(f, fg_color="transparent")
            row.pack(fill="x")
            if len(pv["entries"]) > 1:          # kiválasztás csak listánál van értelme
                w["pick"] = ctk.CTkButton(row, text="Elemek…", width=150, height=34, command=pick, **GREY)
                w["pick"].pack(side="right", padx=(12, 0))
            if pv["thumb"]:
                try:
                    from PIL import Image
                    im = Image.open(io.BytesIO(pv["thumb"])).convert("RGB")
                    tw, th = im.size
                    want = 16 / 9
                    if tw / th > want:       # szélesebb: oldalról vágunk
                        nw = int(th * want)
                        im = im.crop(((tw - nw) // 2, 0, (tw - nw) // 2 + nw, th))
                    else:
                        nh = int(tw / want)
                        im = im.crop((0, (th - nh) // 2, tw, (th - nh) // 2 + nh))
                    img = ctk.CTkImage(light_image=im, dark_image=im, size=(128, 72))
                    st["thumb_img"] = img    # a referenciát tartani kell, különben eltűnik
                    ctk.CTkLabel(row, text="", image=img).pack(side="left", padx=(0, 12))
                except Exception:
                    pass
            txt = ctk.CTkFrame(row, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(txt, text=pv["title"], font=ctk.CTkFont(weight="bold"), anchor="w", justify="left",
                         wraplength=640).pack(anchor="w")
            ctk.CTkLabel(txt, text=pv["sub"], text_color=("gray40", "gray60"), anchor="w").pack(anchor="w")
        render_options()

    # ---- a linkhez illő beállítások (csak azonosított link után jelennek meg)
    def context():
        """Mit tudunk a beírt linkről? None, ha még nincs azonosítva (üres, lekérés alatt, hibás)."""
        urls = [t for t in (w["url"].get().split() if "url" in w else []) if URL_RE.match(t)]
        if not urls:
            return None
        if len(urls) > 1:
            sp = [is_spotify(u) for u in urls]
            return dict(text=f"{len(urls)} link", spotify=any(sp), only_spotify=all(sp), many=True, chapters=0)
        u, pv = urls[0], st["preview"]
        if SUPPORTED_RE.match(u):
            if st["prev_state"] != "ok" or not pv or pv["url"] != u:
                return None
            n, sp = len(pv["entries"]), is_spotify(u)
            if sp:
                text = "Spotify-szám" if n == 1 else "Spotify-lista / album"
            elif n > 1:
                text = "Lejátszási lista"
            else:
                text = "Egyetlen videó / szám" + (f" · {pv['chapters']} fejezet" if pv.get("chapters") else "")
            return dict(text=text, spotify=sp, only_spotify=sp, many=n > 1, chapters=pv.get("chapters", 0))
        return dict(text="Ismeretlen oldal, alapbeállításokkal próbálom", spotify=False, only_spotify=False,
                    many=False, chapters=0, basic=True)

    def features(c):
        """Mely beállítások értelmesek ehhez a linkhez."""
        if not c:
            return set()
        audio = c["spotify"] or S["kind"] == "Hang"     # Spotify-ból mindig hang jön
        f = {"archive"}
        if not c["only_spotify"]:
            f.add("kind")
            f.add("clean")
        if audio:
            f.update(("sort", "normalize"))
            if c["many"]:
                f.add("m3u")
        if c["spotify"]:
            f.add("lyrics")
        if c["chapters"] and not c["spotify"]:
            f.add("split")
        if not c["many"] and not c["spotify"]:
            f.add("cut")
        return f

    def save_cut():
        try:
            if "from" in w:
                st["cut"] = (w["from"].get(), w["to"].get())
        except Exception:
            pass

    def cut_values():
        try:
            return w["from"].get().strip(), w["to"].get().strip()
        except Exception:
            return "", ""

    CHECKS = [("sort", "Mappákba rendezés (Előadó/Album)"), ("clean", "Címek tisztítása"),
              ("archive", "Már letöltöttek kihagyása"), ("normalize", "Hangerő-kiegyenlítés"),
              ("m3u", "Lejátszási lista fájl (.m3u8)"), ("lyrics", "Dalszöveg beágyazása"),
              ("split", "Fejezetek szerinti szétvágás")]

    def render_options(force=False):
        c = context()
        sig = None if c is None else (c["text"], c["spotify"], c["only_spotify"], c["many"], c["chapters"] > 0,
                                      bool(c.get("basic")), S["kind"])
        if sig == st["opt_sig"] and not force:
            return
        st["opt_sig"] = sig
        save_cut()
        holder = w["opt"]
        for ch in holder.winfo_children():
            ch.destroy()
        w.pop("from", None)
        w.pop("to", None)
        if c is None:
            holder.pack_forget()
            return
        f = features(c)
        holder.pack(fill="x", pady=(12, 0), after=w["card"])
        head = ctk.CTkFrame(holder, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(head, text="Letöltési beállítások", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text=c["text"], text_color=MUTED).pack(side="right")

        r1 = ctk.CTkFrame(holder, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(0, 6))
        audio = c["spotify"] and c["only_spotify"] or S["kind"] == "Hang"
        if "kind" in f:
            kind = ctk.CTkSegmentedButton(r1, values=["Hang", "Videó"], command=on_kind)
            kind.set(S["kind"])
            kind.pack(side="left", padx=(0, 16))
        else:
            ctk.CTkLabel(r1, text="Hangként töltöm le (Spotify)", text_color=MUTED).pack(side="left", padx=(0, 16))
        ctk.CTkLabel(r1, text="Formátum:" if audio else "Minőség:").pack(side="left", padx=(0, 8))
        fm = ctk.CTkOptionMenu(r1, values=AUDIO_FORMATS if audio else VIDEO_QUALITIES, width=190, command=on_fmt)
        fm.set(S["afmt"] if audio else S["vfmt"])
        fm.pack(side="left")

        shown = [(k, t) for k, t in CHECKS if k in f]
        if shown:
            grid = ctk.CTkFrame(holder, fg_color="transparent")
            grid.pack(fill="x", padx=16, pady=(6, 4))
            grid.columnconfigure((0, 1), weight=1, uniform="chk")
            for n, (k, t) in enumerate(shown):
                check(grid, k, t).grid(row=n // 2, column=n % 2, sticky="w", pady=5)
        if "cut" in f:
            r3 = ctk.CTkFrame(holder, fg_color="transparent")
            r3.pack(fill="x", padx=16, pady=(6, 0))
            ctk.CTkLabel(r3, text="Kivágás:").pack(side="left", padx=(0, 8))
            w["from"] = ctk.CTkEntry(r3, width=74, placeholder_text="kezdet")
            w["from"].pack(side="left")
            ctk.CTkLabel(r3, text="–").pack(side="left", padx=6)
            w["to"] = ctk.CTkEntry(r3, width=74, placeholder_text="vég")
            w["to"].pack(side="left")
            ctk.CTkLabel(r3, text="pl. 1:30 – 3:45 (üresen hagyva az egészet tölti le)", text_color=MUTED).pack(
                side="left", padx=10)
            if st["cut"][0]:
                w["from"].insert(0, st["cut"][0])
            if st["cut"][1]:
                w["to"].insert(0, st["cut"][1])
        ctk.CTkFrame(holder, height=10, fg_color="transparent").pack()

    def start_preview(url):
        st["prev_url"] = url
        st["prev_seq"] += 1
        seq = st["prev_seq"]
        st["prev_state"], st["preview"], st["sel"], st["cut"] = "loading", None, None, ("", "")
        render_preview()
        update_pick_btn()

        def worker():
            try:
                q.put(("preview", seq, fetch_preview(url), None))
            except Exception as e:
                q.put(("preview", seq, None, str(e) or e.__class__.__name__))

        threading.Thread(target=worker, daemon=True).start()

    def reset_preview():
        st["prev_seq"] += 1
        st["prev_state"], st["preview"], st["prev_url"], st["sel"] = "none", None, "", None
        st["cut"] = ("", "")
        render_preview()
        update_pick_btn()

    def check_preview():
        st["prev_job"] = None
        toks = w["url"].get().split()
        if not toks:
            if st["prev_state"] != "none":
                reset_preview()
            else:
                render_options()
            return
        if len(toks) == 1 and SUPPORTED_RE.match(toks[0]) and toks[0] != st["prev_url"]:
            start_preview(toks[0])
        else:
            if st["prev_state"] != "none" and (len(toks) != 1 or toks[0] != st["prev_url"]):
                reset_preview()          # a beírt szöveg már nem az előnézetben látott link
            render_options()

    def schedule_preview(_=None):
        if st["prev_job"]:
            root.after_cancel(st["prev_job"])
        st["prev_job"] = root.after(700, check_preview)

    def paste():
        try:
            txt = root.clipboard_get().strip()
        except Exception:
            return
        w["url"].delete(0, "end")
        w["url"].insert(0, txt)
        schedule_preview()

    def on_focus(ev):
        """Az ablakra visszalépve, ha a vágólapon támogatott link van és a mező üres, beillesztjük."""
        if ev.widget is not root or not S["clip"]:
            return
        now = time.time()
        if now - st["clip_t"] < 1.5 or "url" not in w:
            return
        st["clip_t"] = now
        if w["url"].get().strip():
            return
        try:
            txt = root.clipboard_get().strip()
        except Exception:
            return
        if SUPPORTED_RE.match(txt) and txt != st["last_clip"]:
            st["last_clip"] = txt
            w["url"].insert(0, txt)
            start_preview(txt)

    # ---- elemkiválasztó
    def update_pick_btn():
        b, sel = w.get("pick"), st["sel"]
        if b is None or not b.winfo_exists():
            return
        if st["fetching"]:
            b.configure(text="Betöltés…", state="disabled")
        else:
            b.configure(state="normal", text=(f"Kiválasztva: {len(sel['ids'])}/{sel['total']}" if sel else "Elemek…"))

    def open_picker(url, entries):
        prev = st["sel"] if (st["sel"] and st["sel"]["url"] == url) else None
        top = ctk.CTkToplevel(root)
        top.title("Elemek kiválasztása")
        top.geometry("680x600")
        top.transient(root)
        top.after(150, top.grab_set)
        ctk.CTkLabel(top, text=f"{len(entries)} elem a listában", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 4))
        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.pack(fill="x", padx=16)
        count = ctk.CTkLabel(bar, text="")
        vars_ = []

        def refresh(*_):
            count.configure(text=f"{sum(v.get() for v in vars_)} kijelölve")

        def set_all(val):
            for v in vars_:
                v.set(val)
            refresh()

        ctk.CTkButton(bar, text="Mind", width=70, command=lambda: set_all(1)).pack(side="left")
        ctk.CTkButton(bar, text="Egyik sem", width=90, command=lambda: set_all(0)).pack(side="left", padx=8)
        count.pack(side="left", padx=8)
        lst = ctk.CTkScrollableFrame(top)
        lst.pack(fill="both", expand=True, padx=16, pady=10)
        for ident, title, dur in entries:
            v = ctk.IntVar(value=1 if (prev is None or ident in prev["ids"]) else 0)
            vars_.append(v)
            d = fmt_dur(dur)
            ctk.CTkCheckBox(lst, text=f"{title}" + (f"   [{d}]" if d else ""), variable=v,
                            command=refresh).pack(anchor="w", pady=2)
        refresh()
        foot = ctk.CTkFrame(top, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(0, 14))

        def ok():
            ids = [e[0] for e, v in zip(entries, vars_) if v.get()]
            st["sel"] = None if len(ids) == len(entries) else {"url": url, "ids": ids, "total": len(entries)}
            if not ids:
                log_write("Nincs kijelölt elem, ezért a lista kiválasztását nem használom.\n")
                st["sel"] = None
            top.destroy()
            update_pick_btn()

        ctk.CTkButton(foot, text="OK", width=100, command=ok).pack(side="right")
        ctk.CTkButton(foot, text="Mégse", width=100, fg_color=("gray75", "gray30"),
                      hover_color=("gray65", "gray40"), text_color=("gray10", "gray90"),
                      command=top.destroy).pack(side="right", padx=8)

    def pick():
        if st["fetching"]:
            return
        toks = w["url"].get().split()
        if len(toks) != 1:
            log_write("Az elemek kiválasztásához pontosan egy linket illessz be.\n")
            return
        url = toks[0]
        pv = st["preview"]
        if pv and pv["url"] == url:           # az előnézetnél már lekértük a lista elemeit
            on_picker(url, pv["entries"], None)
            return
        st["fetching"] = True
        update_pick_btn()

        def worker():
            try:
                q.put(("picker", url, fetch_entries(url), None))
            except Exception as e:
                q.put(("picker", url, None, str(e) or e.__class__.__name__))

        threading.Thread(target=worker, daemon=True).start()

    def on_picker(url, entries, err):
        st["fetching"] = False
        update_pick_btn()
        if err or not entries:
            log_write(f"Nem sikerült lekérdezni a lista elemeit: {err or 'üres lista'}\n")
        elif len(entries) == 1:
            log_write(f"Egyetlen elem van ({entries[0][1]}), nincs mit választani.\n")
            st["sel"] = None
            update_pick_btn()
        else:
            open_picker(url, entries)

    # ---- sor
    def short(text, n=95):
        return text if len(text) <= n else text[:n - 1] + "…"

    def item_by_id(i):
        return next((it for it in st["queue"] if it["id"] == i), None)

    def render_queue():
        f = w["qframe"]
        for c in f.winfo_children():
            c.destroy()
        w["rows"] = {}
        if not st["queue"]:
            ctk.CTkLabel(f, text="A sor üres. Illessz be egy linket, és nyomd meg a Letöltés gombot.",
                         text_color=("gray40", "gray60")).pack(pady=24)
            return
        for it in st["queue"]:
            row = ctk.CTkFrame(f, corner_radius=8, fg_color=("gray88", "gray22"))
            row.pack(fill="x", pady=3, padx=2)
            row.columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=STATUS_TXT[it["status"]], width=74, text_color=STATUS_COL[it["status"]],
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=short(it["label"]), anchor="w").grid(row=0, column=1, sticky="ew", pady=(8, 0))
            info = ctk.CTkLabel(row, text=short(it["info"] or it["err"], 120), anchor="w", font=ctk.CTkFont(size=12),
                                text_color=(STATUS_COL["err"] if it["status"] == "err" and it["err"]
                                            else ("gray40", "gray60")))
            info.grid(row=1, column=1, sticky="ew", pady=(0, 8))
            w["rows"][it["id"]] = info
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=0, column=2, rowspan=2, padx=8)
            grey = dict(width=70, height=28, fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"),
                        text_color=("gray10", "gray90"))
            if it["status"] == "wait":
                ctk.CTkButton(btns, text="Törlés", command=lambda i=it["id"]: remove_item(i), **grey).pack()
            elif it["status"] in ("err", "cancel"):
                ctk.CTkButton(btns, text="Újra", command=lambda i=it["id"]: retry_item(i), **grey).pack()
            elif it["status"] in ("done", "skip"):
                ctk.CTkButton(btns, text="Mappa", command=lambda x=it: reveal(x["files"], x["folder"]),
                              **grey).pack()

    def clear_finished():
        with lock:
            st["queue"] = [it for it in st["queue"] if it["status"] in ("wait", "run")]
        render_queue()

    def remove_item(i):
        with lock:
            st["queue"] = [it for it in st["queue"] if not (it["id"] == i and it["status"] == "wait")]
        render_queue()

    def retry_item(i):
        it = item_by_id(i)
        if it and it["status"] in ("err", "cancel"):
            it.update(status="wait", err="", info="", pct=0)
            render_queue()
            kick()

    # ---- előzmények
    def hist_add(it):
        st["hist"].insert(0, {"t": datetime.now().strftime("%Y-%m-%d %H:%M"), "url": it["url"], "label": it["label"],
                              "status": it["status"], "kind": it["o"]["kind"], "fmt": it["o"]["fmt"],
                              "files": it["files"][:50], "folder": it["folder"]})
        del st["hist"][200:]
        save_history(st["hist"])

    def render_history():
        f = w["hframe"]
        for c in f.winfo_children():
            c.destroy()
        if not st["hist"]:
            ctk.CTkLabel(f, text="Még nincs letöltési előzmény.", text_color=("gray40", "gray60")).pack(pady=24)
            return
        grey = dict(width=84, height=28, fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"),
                    text_color=("gray10", "gray90"))
        for h in st["hist"][:100]:
            row = ctk.CTkFrame(f, corner_radius=8, fg_color=("gray88", "gray22"))
            row.pack(fill="x", pady=3, padx=2)
            row.columnconfigure(1, weight=1)
            ok = h["status"] == "done"
            ctk.CTkLabel(row, text=h["t"], width=118, text_color=("gray40", "gray60"),
                         font=ctk.CTkFont(size=12)).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=short(h["label"]), anchor="w").grid(row=0, column=1, sticky="ew", pady=(8, 0))
            ctk.CTkLabel(row, text=("Kész" if ok else "Hiba") + f" · {'Videó' if h['kind'] == 'video' else 'Hang'} "
                                   f"{h['fmt'] if h['kind'] == 'audio' else ''}".rstrip(),
                         anchor="w", font=ctk.CTkFont(size=12),
                         text_color=STATUS_COL["done" if ok else "err"]).grid(row=1, column=1, sticky="ew",
                                                                              pady=(0, 8))
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=0, column=2, rowspan=2, padx=8)
            if ok:
                ctk.CTkButton(btns, text="Megnyitás", command=lambda x=h: reveal(x["files"], x["folder"]),
                              **grey).pack(side="left", padx=(0, 6))
            ctk.CTkButton(btns, text="Újra", command=lambda x=h: add_urls([x["url"]]), **grey).pack(side="left")

    def clear_history():
        st["hist"] = []
        save_history([])
        render_history()

    # ---- futtatás
    def update_actions():
        busy = st["worker"]
        w["btn"].configure(text="Hozzáadás a sorhoz" if busy else "Letöltés")
        if busy:
            w["cancel"].pack(side="left", padx=(10, 0))
        else:
            w["cancel"].configure(text="Megszakítás", state="normal")
            w["cancel"].pack_forget()
            w["bar"].stop()
            w["bar"].configure(mode="determinate")
            w["bar"].set(0)

    def kick():
        if st["worker"]:
            return
        if not any(it["status"] == "wait" for it in st["queue"]):
            return
        st["worker"] = True
        update_actions()
        threading.Thread(target=worker_loop, daemon=True).start()

    def worker_loop():
        try:
            while not st["cancel"]:
                with lock:
                    it = next((x for x in st["queue"] if x["status"] == "wait"), None)
                if it is None:
                    break
                run_item(it)
        except Exception as e:
            q.put(("log", f"HIBA: {e}\n"))
        finally:
            with lock:
                if st["cancel"]:
                    for x in st["queue"]:
                        if x["status"] == "wait":
                            x["status"] = "cancel"
                st["cancel"] = False
                st["worker"] = False
                st["cur"] = None
            q.put(("worker_done",))

    def run_item(it):
        it["status"] = "run"
        st["cur"] = it["id"]
        q.put(("item", it["id"]))

        def ev(kind, value):
            if kind == "pct":
                it["pct"] = value
            elif kind == "count":
                it["count"] = value
            elif kind == "label":
                it["label"] = value
            pct = f"{int(it['pct'] * 100)}%" if it["pct"] else ""
            cnt = f"{it['count'][0]}/{it['count'][1]}" if it["count"] else ""
            it["info"] = "  ·  ".join(x for x in (cnt, pct) if x)
            q.put(("ipct", it["id"], it["pct"], kind == "label"))

        try:
            res = run(it["url"], it["out"], it["o"], lambda s: q.put(("log", s)), st, ev)
        except Exception as e:
            res = {"code": 1, "files": [], "folder": str(it["out"]), "error": str(e), "skipped": 0}
        it["files"], it["folder"], it["pct"] = res["files"], res["folder"], 0
        if st["cancel"] or res["code"] == 130:
            it.update(status="cancel", info="", err="")
        elif res["code"] == 0:
            skip = res["skipped"] and not res["files"]
            it.update(status="skip" if skip else "done", info="Már letöltötted" if skip else "", err="")
            if it["files"] and it["label"] == it["url"]:
                it["label"] = Path(it["files"][0]).stem
        else:
            it.update(status="err", info="", err=res["error"] or "A letöltés nem sikerült (részletek a Napló fülön).")
        if it["status"] in ("done", "err"):
            hist_add(it)
            q.put(("hist",))
        q.put(("item", it["id"]))

    def cancel_all():
        if not st["worker"]:
            return
        st["cancel"] = True
        w["cancel"].configure(text="Leállítás…", state="disabled")
        kill_tree(st.get("proc"))

    def add_urls(urls, items=None, title=None, c=None, cut=("", "")):
        """c: a link azonosított adatai (context()); ami nem tartozik hozzá (fejezetvágás, kivágás), nem érvényesül."""
        out = Path(w["out"].get().strip() or str(DEFAULT_OUT))
        set_s("out", str(out))
        f = features(c)
        start, end = cut if "cut" in f else ("", "")
        for u in urls:
            audio = is_spotify(u) or S["kind"] == "Hang"      # Spotify-ból mindig hang jön
            base = dict(kind="audio" if audio else "video", fmt=S["afmt"] if audio else S["vfmt"],
                        organize=S["sort"], clean=S["clean"], archive=S["archive"],
                        split=S["split"] and "split" in f, normalize=S["normalize"],
                        m3u=S["m3u"] and ("m3u" in f or c is None),
                        lyrics=S["lyrics"], start=start, end=end)
            it = {"id": st["next_id"], "url": u, "label": title or u, "status": "wait", "pct": 0, "count": None,
                  "info": "", "err": "", "files": [], "folder": str(out), "out": out,
                  "o": default_opts(**base, items=items if len(urls) == 1 else None)}
            st["next_id"] += 1
            st["queue"].append(it)
        w["tabs"].set("Sor")
        render_queue()
        kick()

    def add_from_entry(_=None):
        urls = w["url"].get().split()
        if not urls:
            return
        sel, pv = st["sel"], st["preview"]
        items = None
        if sel and urls == [sel["url"]]:
            items = sel["ids"]
        elif sel:
            log_write("A lista-kiválasztás másik linkre vonatkozott, ezért most nem használom.\n")
        title = pv["title"] if (pv and urls == [pv["url"]] and len(pv["entries"]) > 1) else None
        c, cut = context(), cut_values()        # a reset_preview eltünteti a panelt, ezért előbb kiolvassuk
        w["url"].delete(0, "end")
        reset_preview()
        add_urls(urls, items, title, c, cut)

    def update_tools():
        if st["worker"]:
            log_write("Frissítés csak akkor indítható, ha nincs futó letöltés.\n")
            return
        w["tabs"].set("Napló")
        st["worker"], st["cancel"] = True, False
        update_actions()
        q.put(("mode", "indeterminate"))

        def worker():
            try:
                if FROZEN:
                    q.put(("log", "> a legújabb yt-dlp letöltése (a YouTube-hibák nagy részét ez javítja)…\n"))
                    update_ytdlp_frozen()
                    code = 0
                else:
                    q.put(("log", "> yt-dlp és spotDL frissítése…\n"))
                    code = stream([str(PY), "-m", "pip", "install", "-U", "yt-dlp", "spotdl"],
                                  lambda s: q.put(("log", s)), st)
                if code == 0 and not st["cancel"]:
                    q.put(("log", f"Kész. yt-dlp verzió: {current_ytdlp_version()}\n\n"))
                else:
                    q.put(("log", "A frissítés nem sikerült vagy megszakadt.\n\n"))
            except Exception as e:
                q.put(("log", f"HIBA: {e}\n"))
            finally:
                st["worker"], st["cancel"] = False, False
                q.put(("worker_done",))

        threading.Thread(target=worker, daemon=True).start()

    def auto_update_start():
        """Telepített változatban hetente egyszer, a háttérben megnézi, van-e újabb yt-dlp, és letölti."""
        if not (FROZEN and S["autoupdate"]):
            return
        try:
            last = datetime.strptime(S["last_check"], "%Y-%m-%d") if S["last_check"] else None
        except ValueError:
            last = None
        if last and (datetime.now() - last).days < 7:
            return

        def worker():
            try:
                cur, new = current_ytdlp_version(), latest_ytdlp_version()
                if vkey(new) > vkey(cur):
                    update_ytdlp_frozen()
                    q.put(("log", f"A yt-dlp automatikusan frissült: {cur} → {new}\n\n"))
                set_s("last_check", datetime.now().strftime("%Y-%m-%d"))
            except PermissionError:
                pass            # épp használatban van: legközelebb újra próbáljuk
            except Exception:
                pass            # nincs net vagy a GitHub nem válaszol: legközelebb újra próbáljuk

        threading.Thread(target=worker, daemon=True).start()

    def pump():
        try:
            while True:
                m = q.get_nowait()
                k = m[0]
                if k == "log":
                    log_write(m[1])
                elif k == "item":
                    render_queue()
                    if st["cur"] is None or item_by_id(m[1]) is None or item_by_id(m[1])["status"] != "run":
                        w["bar"].stop()
                        w["bar"].configure(mode="determinate")
                        w["bar"].set(0)
                elif k == "ipct":
                    it = item_by_id(m[1])
                    if it and "rows" in w and m[1] in w["rows"]:
                        lbl = w["rows"][m[1]]
                        lbl.configure(text=short(it["info"], 120))
                    if m[3]:
                        render_queue()
                    if m[1] == st["cur"]:
                        w["bar"].set(m[2])
                elif k == "mode":
                    w["bar"].configure(mode=m[1])
                    if m[1] == "indeterminate":
                        w["bar"].start()
                elif k == "ver":
                    try:
                        w["ver"].configure(text=f"verzió: {m[1]}")
                    except Exception:
                        pass            # közben bezárták a beállítások ablakot
                elif k == "hist":
                    render_history()
                elif k == "worker_done":
                    update_actions()
                    kick()          # ha közben új elem került a sorba
                elif k == "picker":
                    on_picker(m[1], m[2], m[3])
                elif k == "preview":
                    if m[1] == st["prev_seq"]:
                        if m[3]:
                            st["prev_state"], st["prev_msg"] = "err", m[3]
                        else:
                            st["prev_state"], st["preview"] = "ok", m[2]
                        render_preview()
        except queue.Empty:
            pass
        root.after(100, pump)

    def build():
        old = {k: w[k].get() for k in ("url",) if k in w}
        save_cut()
        for k in ("from", "to", "pick", "settings"):
            w.pop(k, None)
        st["opt_sig"] = None
        cur_tab = w["tabs"].get() if "tabs" in w else "Sor"
        for c in root.winfo_children():
            c.destroy()
        root.configure(fg_color=ctk.ThemeManager.theme["CTk"]["fg_color"])
        grey = GREY

        page = ctk.CTkFrame(root, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=22, pady=18)

        # fejléc: cím + beállítások
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="Zene letöltő", font=ctk.CTkFont(size=28, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="YouTube · Spotify · SoundCloud · Bandcamp és még sok más",
                     text_color=MUTED).pack(side="left", padx=(14, 0), pady=(10, 0))
        ctk.CTkButton(head, text="Beállítások", width=110, command=open_settings, **grey).pack(side="right")

        # link kártya
        card = ctk.CTkFrame(page, corner_radius=14)
        w["card"] = card
        card.pack(fill="x", pady=(18, 0))
        ctk.CTkLabel(card, text="Link (több is lehet, szóközzel elválasztva)",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=16, pady=(14, 4))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        w["url"] = ctk.CTkEntry(row, height=40, placeholder_text="Illeszd be a videó, szám, album vagy lista linkjét…")
        w["url"].pack(side="left", fill="x", expand=True)
        if old.get("url"):
            w["url"].insert(0, old["url"])
        w["url"].bind("<Return>", add_from_entry)
        w["url"].bind("<KeyRelease>", schedule_preview)
        ctk.CTkButton(row, text="Beillesztés", width=100, height=40, command=paste, **grey).pack(side="left", padx=(8, 0))
        w["prev"] = ctk.CTkFrame(card, fg_color="transparent")     # előnézet (csak ha van mit mutatni)

        # a linkhez illő letöltési beállítások (a render_options tölti fel, azonosított link nélkül rejtett)
        w["opt"] = ctk.CTkFrame(page, corner_radius=14)

        # mentési mappa
        r4 = ctk.CTkFrame(page, fg_color="transparent")
        r4.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(r4, text="Mentés ide:").pack(side="left", padx=(2, 8))
        w["out"] = ctk.CTkEntry(r4, height=34)
        w["out"].insert(0, S["out"])
        w["out"].pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r4, text="Tallózás", width=90, height=34, command=browse, **grey).pack(side="left", padx=(8, 0))
        ctk.CTkButton(r4, text="Megnyitás", width=90, height=34, command=open_folder, **grey).pack(
            side="left", padx=(8, 0))

        # letöltés gomb + megszakítás + sáv
        act = ctk.CTkFrame(page, fg_color="transparent")
        act.pack(fill="x", pady=(12, 0))
        w["btn"] = ctk.CTkButton(act, text="Letöltés", height=46, font=ctk.CTkFont(size=16, weight="bold"),
                                 command=add_from_entry)
        w["btn"].pack(side="left", fill="x", expand=True)
        w["cancel"] = ctk.CTkButton(act, text="Megszakítás", height=46, width=140, fg_color=("#c0392b", "#a93226"),
                                    hover_color=("#a93226", "#922b21"), command=cancel_all)
        w["bar"] = ctk.CTkProgressBar(page, height=8)
        w["bar"].set(0)
        w["bar"].pack(fill="x", pady=(10, 0))

        # fülek: sor / napló / előzmények
        w["tabs"] = ctk.CTkTabview(page, corner_radius=12)
        w["tabs"].pack(fill="both", expand=True, pady=(12, 0))
        for name in ("Sor", "Napló", "Előzmények"):
            w["tabs"].add(name)
        tq = w["tabs"].tab("Sor")
        tb = ctk.CTkFrame(tq, fg_color="transparent")
        tb.pack(fill="x")
        ctk.CTkButton(tb, text="Kész elemek törlése", width=150, height=28, command=clear_finished, **grey).pack(
            side="right")
        w["qframe"] = ctk.CTkScrollableFrame(tq, fg_color="transparent")
        w["qframe"].pack(fill="both", expand=True, pady=(6, 0))
        w["log"] = ctk.CTkTextbox(w["tabs"].tab("Napló"), corner_radius=12, font=ctk.CTkFont(family="Consolas", size=12),
                                  wrap="word", state="disabled", fg_color=("gray96", "gray12"),
                                  text_color=("gray15", "gray85"))
        w["log"].pack(fill="both", expand=True)
        th = ctk.CTkFrame(w["tabs"].tab("Előzmények"), fg_color="transparent")
        th.pack(fill="x")
        ctk.CTkButton(th, text="Előzmények törlése", width=150, height=28, command=clear_history, **grey).pack(
            side="right")
        w["hframe"] = ctk.CTkScrollableFrame(w["tabs"].tab("Előzmények"), fg_color="transparent")
        w["hframe"].pack(fill="both", expand=True, pady=(6, 0))

        if log_buf:
            w["log"].configure(state="normal")
            w["log"].insert("end", "".join(log_buf))
            w["log"].see("end")
            w["log"].configure(state="disabled")
        render_queue()
        render_history()
        render_preview()
        update_pick_btn()
        update_actions()
        w["tabs"].set(cur_tab)
        if st["worker"]:
            w["bar"].configure(mode="indeterminate")
            w["bar"].start()
        w["url"].focus()

    build()
    root.bind("<FocusIn>", on_focus, add="+")
    pump()
    root.after(2500, auto_update_start)
    root.mainloop()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) > 2 and sys.argv[1] == "--tool":
        tool_main(sys.argv[2], sys.argv[3:])
    elif len(sys.argv) > 1:
        cli()
    else:
        gui()
