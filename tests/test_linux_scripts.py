"""A Linuxos telepítő (install.sh, uninstall.sh, zenelero.desktop) viselkedését rögzítő tesztek.

A scriptek bash-sel futnak, a rendszerprogramok (python3, ffmpeg, deno, pacman, sudo) csonkok, a HOME ideiglenes
mappa: a teszt nem nyúl a valódi rendszerhez. Ha nincs működő bash, a tesztek kimaradnak."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A csomag szerkezete: ugyanez kerül a Linux-csomag (tar) gyökerébe.
PACKAGE_FILES = {
    "zenelero.py": "zenelero.py",
    "plat.py": "plat.py",
    "plat_windows.py": "plat_windows.py",
    "plat_linux.py": "plat_linux.py",
    "spotify_list.py": "spotify_list.py",
    "requirements.txt": "requirements.txt",
    "assets/icon.png": "assets/icon.png",
    "linux/zenelero.desktop": "zenelero.desktop",
    "linux/install.sh": "install.sh",
    "linux/uninstall.sh": "uninstall.sh",
}

PYTHON3_STUB = r'''#!/usr/bin/env bash
# `python3 -m venv D`: létrehozza a D/bin/python és D/bin/pip csonkot (a hívást a csonkmappa venv.log-jába naplózza);
# a pip az argumentumait a D/pip.log-ba írja.
# `python3 -c ...`: 0-val tér vissza (STUB_NO_TK esetén a tkinter-próba elbukik).
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
    dir="${!#}"
    mkdir -p "$dir/bin"
    echo "$dir" >> "$(dirname "$0")/venv.log"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$dir/bin/python"
    printf '#!/usr/bin/env bash\necho "$@" >> "$(dirname "$0")/../pip.log"\n' > "$dir/bin/pip"
    chmod +x "$dir/bin/python" "$dir/bin/pip"
    exit 0
fi
if [ -n "${STUB_NO_TK:-}" ] && [ "${1:-}" = "-c" ] && [ "${2:-}" = "import tkinter" ]; then
    exit 1
fi
exit 0
'''
PACMAN_STUB = '#!/usr/bin/env bash\necho "$@" >> "$(dirname "$0")/pacman.log"\n'
SUDO_STUB = '#!/usr/bin/env bash\nexec "$@"\n'
PLAIN_STUB = '#!/usr/bin/env bash\nexit 0\n'

# bash -c wrapper: a HOME-ot és a PATH-ot a bash-en belül, bash-formában állítja be (nincs Windows-útvonal-átalakítás),
# a PATH elején a csonkmappa, mögötte csak a bash saját mappája (coreutils): a valódi ffmpeg/deno nem szivároghat be.
# Linuxon (POSIX) a csonkmappa mögött a $3 áll: csak a scriptek által használt rendszereszközök symlinkjei, így a
# valódi ffmpeg/deno/pacman/update-desktop-database sem szivároghat be. Üres $3 esetén (Windows, Git Bash) a bash saját mappája.
WRAPPER = ('export HOME="$1" PATH="$2:${3:-${BASH%/*}}"; shift 3; '
           'while [ "$1" != "--" ]; do export "$1"; shift; done; shift; exec "$BASH" "$@"')

# A telepítő- és csonkscriptek által használt külső programok (a többi bash-beépített).
SYSTEM_TOOLS = ("bash", "env", "dirname", "mkdir", "rm", "cp", "cat", "chmod")


def _bash_works(exe):
    """Működő bash-e (a PATH-on lehet a WSL-es bash.exe, ami disztró nélkül hibázik)."""
    try:
        r = subprocess.run([exe, "-c", "echo ok"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == "ok"


def find_bash():
    """Működő bash útvonala, vagy None. Előbb a PATH, utána a Git telepítés (usr/bin/bash.exe)."""
    candidates = [shutil.which("bash")]
    git = shutil.which("git")
    if git:
        candidates.append(str(Path(git).resolve().parent.parent / "usr" / "bin" / "bash.exe"))
    for exe in candidates:
        if exe and Path(exe).exists() and _bash_works(exe):
            return exe
    return None


def bash_path(p):
    """Windowsos útvonal bash-formára (C:\\x -> /c/x); máshol változatlan."""
    s = str(p)
    if os.name != "nt":
        return s
    m = re.match(r"^([A-Za-z]):[\\/]*(.*)$", s)
    if not m:
        return s.replace("\\", "/")
    return "/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/")


BASH = find_bash()


def write_lf(path, text, executable=False):
    """Szöveg írása LF sorvéggel; `executable` esetén futtatható is (Linuxon a csonkoknak kell a jog)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    if executable:
        path.chmod(0o755)


@unittest.skipUnless(BASH, "nincs működő bash: a telepítő-scriptek tesztjei kimaradnak")
class LinuxScriptsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.pkg = tmp / "csomag"
        self.stubs = tmp / "csonkok"
        self.tools = tmp / "eszkozok"
        self.home = tmp / "home"
        self.home.mkdir()
        self.build_package()
        self.make_stubs()
        self.make_tools()

    def build_package(self):
        for src, dst in PACKAGE_FILES.items():
            data = (ROOT / src).read_bytes()
            target = self.pkg / dst
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data.replace(b"\r\n", b"\n"))

    def make_stubs(self, omit=()):
        self.stubs.mkdir(exist_ok=True)
        content = {"python3": PYTHON3_STUB, "ffmpeg": PLAIN_STUB, "deno": PLAIN_STUB,
                   "pacman": PACMAN_STUB, "sudo": SUDO_STUB}
        for name, text in content.items():
            if name not in omit:
                write_lf(self.stubs / name, text, executable=True)

    def make_tools(self):
        """POSIX-on a csonkmappa mögötti PATH-elem: a SYSTEM_TOOLS symlinkjei. Windowson nincs (a bash mappája szolgál)."""
        if os.name == "nt":
            return
        self.tools.mkdir()
        for name in SYSTEM_TOOLS:
            real = BASH if name == "bash" else shutil.which(name)
            if real:
                (self.tools / name).symlink_to(real)

    def bash(self, *argv, extra=(), env=None):
        """A bash a csonkokkal a PATH-on, HOME = self.home; az XDG_* változók törölve (az extra-ban adhatók meg)."""
        run_env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        run_env.update(env or {})
        tools = bash_path(self.tools) if self.tools.is_dir() else ""
        cmd = [BASH, "-c", WRAPPER, "_", bash_path(self.home), bash_path(self.stubs), tools, *extra, "--", *argv]
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=run_env, timeout=120)

    def script(self, name, *args, **kw):
        return self.bash(bash_path(self.pkg / name), *args, **kw)

    def install(self, *args, **kw):
        return self.script("install.sh", *args, **kw)

    def uninstall(self, *args, **kw):
        return self.script("uninstall.sh", *args, **kw)

    def assertOk(self, r):
        self.assertEqual(r.returncode, 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")

    @property
    def base(self):
        return self.home / ".local" / "share" / "zenelero"

    def test_szintaxis(self):
        for name in ("install.sh", "uninstall.sh"):
            with self.subTest(script=name):
                r = self.bash("-n", bash_path(self.pkg / name))
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_telepites_letrehozza_a_fajlokat(self):
        r = self.install()
        self.assertOk(r)
        launcher = (self.home / ".local" / "bin" / "zenelero").read_text(encoding="utf-8")
        self.assertIn("/venv/bin/python", launcher)
        self.assertIn("/app/zenelero.py", launcher)
        self.assertIn(bash_path(self.base), launcher)
        desktop = (self.home / ".local" / "share" / "applications" / "zenelero.desktop").read_text(encoding="utf-8")
        exec_lines = [ln for ln in desktop.splitlines() if ln.startswith("Exec=")]
        self.assertEqual(exec_lines, ["Exec=" + bash_path(self.home) + "/.local/bin/zenelero"])
        self.assertNotIn("@EXEC@", desktop)
        self.assertIn("Name=Zene letöltő", desktop)
        self.assertTrue((self.home / ".local/share/icons/hicolor/256x256/apps/zenelero.png").is_file())
        pip_log = (self.base / "venv" / "pip.log").read_text(encoding="utf-8")
        self.assertIn("-r", pip_log)
        self.assertIn("requirements.txt", pip_log)
        app = self.base / "app"
        self.assertTrue((app / "zenelero.py").is_file())
        self.assertTrue((app / "assets" / "icon.png").is_file())
        for name in ("install.sh", "uninstall.sh", "zenelero.desktop"):
            self.assertFalse((app / name).exists(), name)

    def test_ujrafuttatas_nem_nyul_a_beallitasokhoz(self):
        settings = self.home / ".config" / "zenelero" / "settings.json"
        write_lf(settings, '{"x": 1}')
        self.assertOk(self.install())
        stale = self.base / "app" / "regi_fajl.txt"
        stale.write_text("x", encoding="utf-8")
        marker = self.base / "venv" / "marker"
        marker.write_text("x", encoding="utf-8")
        self.assertOk(self.install())
        self.assertEqual(settings.read_text(encoding="utf-8"), '{"x": 1}')
        self.assertFalse(stale.exists(), "az app mappa újraíródik")
        self.assertTrue(marker.exists(), "a meglévő venv megmarad")
        self.assertEqual([p.name for p in (self.home / ".local/share/applications").iterdir()], ["zenelero.desktop"])

    def test_hianyzo_csomag_megall_telepites_elott(self):
        self.stubs.joinpath("ffmpeg").unlink()
        if self.bash("-c", "command -v ffmpeg").returncode == 0:
            self.skipTest("a rendszer bash mappájában valódi ffmpeg van: nem lehet kizárni")
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ffmpeg", r.stderr)
        self.assertIn("pacman -S --needed ffmpeg", r.stderr)
        self.assertEqual(list(self.home.iterdir()), [], "semmi nem jöhetett létre")

    def test_hianyzo_tkinter_a_tk_csomagot_kerti(self):
        r = self.install(extra=("STUB_NO_TK=1",))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pacman -S --needed tk", r.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_deps_kapcsolo_felrakja_a_hianyzot(self):
        self.stubs.joinpath("deno").unlink()
        if self.bash("-c", "command -v deno").returncode == 0:
            self.skipTest("a rendszer bash mappájában valódi deno van: nem lehet kizárni")
        r = self.install("--deps")
        self.assertOk(r)
        pacman_log = (self.stubs / "pacman.log").read_text(encoding="utf-8")
        self.assertIn("-S --needed --noconfirm deno", pacman_log)
        self.assertTrue((self.home / ".local" / "bin" / "zenelero").is_file())

    def test_xdg_valtozok(self):
        data = self.home.parent / "adat"
        config = self.home.parent / "beallitas"
        extra = (f"XDG_DATA_HOME={bash_path(data)}", f"XDG_CONFIG_HOME={bash_path(config)}")
        write_lf(config / "zenelero" / "settings.json", "{}")
        self.assertOk(self.install(extra=extra))
        self.assertTrue((data / "zenelero" / "app" / "zenelero.py").is_file())
        self.assertTrue((data / "applications" / "zenelero.desktop").is_file())
        self.assertTrue((data / "icons/hicolor/256x256/apps/zenelero.png").is_file())
        self.assertTrue((self.home / ".local" / "bin" / "zenelero").is_file())
        self.assertFalse((self.home / ".local" / "share").exists())
        self.assertOk(self.uninstall("--purge", extra=extra))
        self.assertFalse((data / "zenelero").exists())
        self.assertFalse((config / "zenelero").exists())

    def test_eltavolitas(self):
        settings = self.home / ".config" / "zenelero" / "settings.json"
        write_lf(settings, "{}")
        self.assertOk(self.install())
        self.assertOk(self.uninstall())
        self.assertFalse(self.base.exists())
        self.assertFalse((self.home / ".local/bin/zenelero").exists())
        self.assertFalse((self.home / ".local/share/applications/zenelero.desktop").exists())
        self.assertFalse((self.home / ".local/share/icons/hicolor/256x256/apps/zenelero.png").exists())
        self.assertTrue(settings.is_file(), "a beállítások megmaradnak")
        self.assertOk(self.uninstall("--purge"))
        self.assertFalse(settings.parent.exists(), "--purge a beállításokat is törli")

    def test_eltavolitas_ketszer(self):
        self.assertOk(self.install())
        self.assertOk(self.uninstall("--purge"))
        self.assertOk(self.uninstall("--purge"))

    def test_eltavolitas_telepites_nelkul(self):
        self.assertOk(self.uninstall())

    def venv_hivasok(self):
        log = self.stubs / "venv.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def test_serult_venv_ujraepul(self):
        settings = self.home / ".config" / "zenelero" / "settings.json"
        write_lf(settings, '{"x": 1}')
        self.assertOk(self.install())
        self.assertEqual(len(self.venv_hivasok()), 1)
        marker = self.base / "venv" / "marker"
        marker.write_text("x", encoding="utf-8")
        write_lf(self.base / "venv" / "bin" / "python", "#!/usr/bin/env bash\nexit 1\n", executable=True)
        r = self.install()
        self.assertOk(r)
        self.assertEqual(len(self.venv_hivasok()), 2, "a törött venvet újra kell építeni")
        self.assertFalse(marker.exists(), "az újraépített venv tiszta")
        self.assertTrue((self.base / "venv" / "pip.log").is_file(), "az újraépített venvbe a pip telepít")
        self.assertEqual(settings.read_text(encoding="utf-8"), '{"x": 1}')

    def test_hianyzo_venv_python_is_ujraepul(self):
        self.assertOk(self.install())
        (self.base / "venv" / "bin" / "python").unlink()
        self.assertOk(self.install())
        self.assertEqual(len(self.venv_hivasok()), 2)

    def test_ep_venv_nem_epul_ujra(self):
        self.assertOk(self.install())
        self.assertOk(self.install())
        self.assertEqual(len(self.venv_hivasok()), 1)

    def test_forrasmappabol_futtatva_megall_es_nem_torol(self):
        forras = self.pkg.parent / "repo_linux"
        for name in ("install.sh", "zenelero.desktop"):
            target = forras / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / "linux" / name).read_bytes().replace(b"\r\n", b"\n"))
        regi = self.base / "app" / "meglevo.txt"
        write_lf(regi, "x")
        r = self.bash(bash_path(forras / "install.sh"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("kicsomagolt csomag", r.stderr)
        self.assertTrue(regi.is_file(), "a meglévő app mappa érintetlen")
        self.assertFalse((self.home / ".local" / "bin").exists())

    def test_install_ismeretlen_kapcsolo_semmit_nem_csinal(self):
        r = self.install("--foo", "--deps")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("--foo", r.stderr)
        self.assertEqual(list(self.home.iterdir()), [], "semmi nem jöhetett létre")
        self.assertFalse((self.stubs / "pacman.log").exists(), "a --deps sem futhatott le")

    def test_install_help_csak_kiir(self):
        for flag in ("--help", "-h"):
            with self.subTest(flag=flag):
                r = self.install(flag)
                self.assertOk(r)
                self.assertIn("--deps", r.stdout)
                self.assertEqual(list(self.home.iterdir()), [])

    def test_uninstall_ismeretlen_kapcsolo_nem_torol(self):
        settings = self.home / ".config" / "zenelero" / "settings.json"
        write_lf(settings, "{}")
        self.assertOk(self.install())
        for args in (("--foo",), ("--purge", "--foo"), ("--foo", "--purge")):
            with self.subTest(args=args):
                r = self.uninstall(*args)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("--foo", r.stderr)
                self.assertTrue((self.base / "app" / "zenelero.py").is_file())
                self.assertTrue((self.home / ".local/bin/zenelero").is_file())
                self.assertTrue(settings.is_file())

    def test_uninstall_help_csak_kiir(self):
        settings = self.home / ".config" / "zenelero" / "settings.json"
        write_lf(settings, "{}")
        self.assertOk(self.install())
        for flag in ("--help", "-h"):
            with self.subTest(flag=flag):
                r = self.uninstall(flag)
                self.assertOk(r)
                self.assertIn("--purge", r.stdout)
                self.assertTrue((self.base / "app" / "zenelero.py").is_file())
                self.assertTrue(settings.is_file())


class DesktopFileTest(unittest.TestCase):
    def test_az_asztali_bejegyzes_kulcsai(self):
        text = (ROOT / "linux" / "zenelero.desktop").read_text(encoding="utf-8")
        fields = dict(ln.split("=", 1) for ln in text.splitlines() if "=" in ln)
        self.assertEqual(fields["Type"], "Application")
        self.assertEqual(fields["Name"], "Zene letöltő")
        self.assertTrue(fields["Comment"].strip())
        self.assertEqual(fields["Exec"], "@EXEC@")
        self.assertEqual(fields["Icon"], "zenelero")
        self.assertEqual(fields["Terminal"], "false")
        self.assertEqual(fields["Categories"], "AudioVideo;Audio;Network;")

    def test_a_kovetelmenyek_negy_sora(self):
        lines = [ln.strip() for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        self.assertEqual(sorted(lines), sorted(["customtkinter", "pillow", "spotdl", "yt-dlp[default]"]))

    def test_az_ikon_256_negyzetes_png(self):
        data = (ROOT / "assets" / "icon.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(data[16:20], "big"), 256)
        self.assertEqual(int.from_bytes(data[20:24], "big"), 256)


if __name__ == "__main__":
    unittest.main()
