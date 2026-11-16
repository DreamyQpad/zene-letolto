"""A Linux-csomag építése a (Windowsos) forrásból: out/Zenelero-linux-<verzió>.tar.gz, másolat a Dokumentumok\\telepitok mappába.

    .venv\\Scripts\\python build_linux.py

A csomag ugyanaz a kód, mint a Windowsos változat; kimarad belőle a Windows-réteg (plat_windows), a build- és tesztfájlok.
A csomagoló ellenőrzi, hogy minden betett modul lefordul, semmi nem hivatkozik a csomagból hiányzó modulra, és minden
adatfájl megvan. A kimenet reprodukálható: ugyanabból a forrásból ugyanaz a bájtsor készül (a tar és a gzip időbélyege 0)."""
import ast
import gzip
import io
import re
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCLUDE = {"plat_windows.py", "build_linux.py"}
PLATFORM_ONLY = {"plat_windows"}                       # a plat.py csak win32-n tölti be
MAIN_SCRIPT = "zenelero.py"
DATA_FILES = ["requirements.txt", "assets/icon.png", "README.md", "LINUX.md"]
SCRIPTS = {"linux/install.sh": "install.sh", "linux/uninstall.sh": "uninstall.sh"}
DESKTOP = {"linux/zenelero.desktop": "zenelero.desktop"}
# Csak ezeknél cseréljük a CRLF-et LF-re; a bináris fájl (PNG) érintetlen marad.
TEXT_SUFFIXES = (".py", ".sh", ".md", ".desktop", ".txt")


def version():
    match = re.search(r'^VERSION = "(.+?)"', (ROOT / MAIN_SCRIPT).read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        sys.exit(f"Nincs VERSION a {MAIN_SCRIPT}-ban.")
    return match.group(1)


def local_imports(source, modules, filename="<forrás>"):
    """A forrásban importált helyi modulok (a `modules` halmaz elemei közül)."""
    found = set()
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        else:
            continue
        found |= {name.split(".")[0] for name in names} & modules
    return found


def find_problems(sources, modules):
    """A csomagba kerülő források hibái. `sources`: fájlnév -> forrásszöveg; `modules`: az összes helyi modul neve
    (a kimaradókkal együtt). Üres lista = rendben."""
    packaged = {Path(name).stem for name in sources}
    problems = []
    for name, text in sorted(sources.items()):
        try:
            compile(text, name, "exec")
            missing = local_imports(text, modules, name) - packaged - PLATFORM_ONLY
        except SyntaxError as error:
            problems.append(f"{name}: szintaxishiba: {error}")
            continue
        if missing:
            problems.append(f"{name}: a csomagból hiányzó modul: {', '.join(sorted(missing))}")
    return problems


def build(out_dir, docs_dir=None):
    """Megépíti a tar.gz-t az `out_dir`-be; `docs_dir` megadásakor oda is másol. Visszatér a tar útjával."""
    ver = version()
    sources = sorted(path for path in ROOT.glob("*.py") if path.name not in EXCLUDE)
    problems = find_problems({path.name: path.read_text(encoding="utf-8") for path in sources},
                             {path.stem for path in ROOT.glob("*.py")})
    for name in DATA_FILES + list(SCRIPTS) + list(DESKTOP):
        if not (ROOT / name).is_file():
            problems.append(f"hiányzó fájl: {name}")
    if problems:
        sys.exit("A csomag nem építhető:\n  " + "\n  ".join(problems))

    top = f"zenelero-{ver}"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"Zenelero-linux-{ver}.tar.gz"

    def add(tar, data, arcname, mode):
        if arcname.endswith(TEXT_SUFFIXES):
            data = data.replace(b"\r\n", b"\n")
        info = tarfile.TarInfo(f"{top}/{arcname}")
        info.size, info.mode, info.uname, info.gname = len(data), mode, "", ""
        tar.addfile(info, io.BytesIO(data))

    with open(target, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz, \
            tarfile.open(fileobj=gz, mode="w") as tar:
        for path in sources:
            add(tar, path.read_bytes(), path.name, 0o644)
        for name in DATA_FILES:
            add(tar, (ROOT / name).read_bytes(), name, 0o644)
        for src, dst in SCRIPTS.items():
            add(tar, (ROOT / src).read_bytes(), dst, 0o755)
        for src, dst in DESKTOP.items():
            add(tar, (ROOT / src).read_bytes(), dst, 0o644)

    if docs_dir is not None:
        docs_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, docs_dir / target.name)
    return target


def main():
    docs = Path.home() / "Documents" / "telepitok"
    target = build(ROOT / "out", docs)
    print(f"Kész: {target} ({target.stat().st_size} bájt)")
    print(f"Másolat: {docs / target.name}")


if __name__ == "__main__":
    main()
