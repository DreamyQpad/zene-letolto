"""A Linux-csomag (tar.gz) építését rögzítő tesztek: a csomag neve, tartalma, módjai, sortörései, a csomagoló
ellenőrzései (szintaxis, hiányzó helyi import, hiányzó adatfájl) és az építés reprodukálhatósága."""
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_linux  # noqa: E402
import zenelero  # noqa: E402

TEXT_SUFFIXES = (".py", ".sh", ".md", ".desktop", ".txt")


class BuildLinuxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        cls.tar_path = build_linux.build(cls.out)
        cls.top = f"zenelero-{zenelero.VERSION}"
        with tarfile.open(cls.tar_path) as tar:
            cls.members = {member.name: member for member in tar.getmembers()}
            cls.data = {name: tar.extractfile(member).read() for name, member in cls.members.items() if member.isfile()}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def name(self, relative):
        return f"{self.top}/{relative}"

    def test_a_tar_neve_es_gyokere(self):
        self.assertEqual(self.tar_path, self.out / f"Zenelero-linux-{zenelero.VERSION}.tar.gz")
        self.assertTrue(self.tar_path.is_file())
        for name in self.members:
            self.assertTrue(name.startswith(self.top + "/"), name)

    def test_tartalom(self):
        for relative in ("zenelero.py", "plat.py", "plat_linux.py", "spotify_list.py", "requirements.txt",
                         "assets/icon.png", "README.md", "LINUX.md", "install.sh", "uninstall.sh", "zenelero.desktop"):
            self.assertIn(self.name(relative), self.data, relative)

    def test_kimarad_a_windowsos_resz(self):
        for relative in ("plat_windows.py", "build_linux.py", "build.ps1", "zenelero.bat"):
            self.assertNotIn(self.name(relative), self.members, relative)
        for name in self.members:
            relative = name[len(self.top) + 1:]
            self.assertFalse(relative.startswith(("tests/", "build_installer/", "docs/", "linux/")), name)

    def test_modok(self):
        for relative, mode in (("install.sh", 0o755), ("uninstall.sh", 0o755),
                               ("zenelero.py", 0o644), ("plat.py", 0o644), ("zenelero.desktop", 0o644),
                               ("requirements.txt", 0o644), ("LINUX.md", 0o644), ("assets/icon.png", 0o644)):
            self.assertEqual(self.members[self.name(relative)].mode, mode, relative)

    def test_nincs_crlf(self):
        szoveges = [name for name in self.data if name.endswith(TEXT_SUFFIXES)]
        self.assertIn(self.name("zenelero.desktop"), szoveges)
        self.assertIn(self.name("install.sh"), szoveges)
        for name in szoveges:
            self.assertNotIn(b"\r\n", self.data[name], name)

    def test_a_desktop_exec_sora_pontosan_illeszkedik(self):
        lines = self.data[self.name("zenelero.desktop")].split(b"\n")
        self.assertIn(b"Exec=@EXEC@", lines)

    def test_az_ikon_bajtazonos_a_forrassal(self):
        self.assertEqual(self.data[self.name("assets/icon.png")], (ROOT / "assets" / "icon.png").read_bytes())

    def test_masolat_a_docs_mappaba(self):
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as docs:
            target = build_linux.build(Path(out), Path(docs))
            copy = Path(docs) / target.name
            self.assertTrue(copy.is_file())
            self.assertEqual(copy.read_bytes(), target.read_bytes())
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as docs:
            build_linux.build(Path(out))
            self.assertEqual(list(Path(docs).iterdir()), [])

    def test_ketszer_futtatva_ugyanaz_a_kimenet(self):
        with tempfile.TemporaryDirectory() as out:
            masodik = build_linux.build(Path(out))
            self.assertEqual(masodik.read_bytes(), self.tar_path.read_bytes())

    def test_a_gzip_es_a_tar_idobelyege_nulla(self):
        raw = self.tar_path.read_bytes()
        self.assertEqual(raw[:2], b"\x1f\x8b")
        self.assertEqual(raw[4:8], b"\0\0\0\0", "a gzip-fejléc mtime mezője")
        for name, member in self.members.items():
            self.assertEqual(member.mtime, 0, name)

    def test_version_a_zenelero_pyabol(self):
        self.assertEqual(build_linux.version(), zenelero.VERSION)


class EllenorzesTest(unittest.TestCase):
    def test_hianyzo_helyi_import_eszlelese(self):
        problems = build_linux.find_problems({"a.py": "import b\n"}, {"a", "b", "c"})
        self.assertEqual(len(problems), 1)
        self.assertIn("a.py", problems[0])
        self.assertIn("b", problems[0])

    def test_hianyzo_import_fuggvenyben_es_from_importtal_is(self):
        sources = {"a.py": "def f():\n    from c import x\n"}
        problems = build_linux.find_problems(sources, {"a", "c"})
        self.assertEqual(len(problems), 1)
        self.assertIn("c", problems[0])

    def test_a_csomagban_levo_modul_importja_rendben(self):
        self.assertEqual(build_linux.find_problems({"a.py": "import b\n", "b.py": "x = 1\n"}, {"a", "b"}), [])

    def test_a_kulso_csomag_nem_helyi_import(self):
        self.assertEqual(build_linux.find_problems({"a.py": "import json\nfrom os import path\n"}, {"a"}), [])

    def test_a_windowsos_modul_hivatkozasa_megengedett(self):
        source = "from plat_windows import *\n"
        self.assertEqual(build_linux.find_problems({"plat.py": source}, {"plat", "plat_windows"}), [])

    def test_szintaxishiba_eszlelese(self):
        problems = build_linux.find_problems({"a.py": "def (:\n"}, {"a"})
        self.assertEqual(len(problems), 1)
        self.assertIn("szintaxishiba", problems[0])

    def test_a_build_leall_a_hianyzo_adatfajlnal(self):
        with tempfile.TemporaryDirectory() as out:
            with mock.patch.object(build_linux, "DATA_FILES", build_linux.DATA_FILES + ["nincs_ilyen.txt"]):
                with self.assertRaises(SystemExit) as raised:
                    build_linux.build(Path(out))
        self.assertIn("nincs_ilyen.txt", str(raised.exception))
        self.assertIn("hiányzó fájl", str(raised.exception))

    def test_a_crlf_csere_csak_a_szoveges_fajlokat_erinti(self):
        png = b"\x89PNG\r\n\x1a\n\x00\r\n\x01"
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as src:
            fake = Path(src)
            (fake / "assets").mkdir()
            (fake / "linux").mkdir()
            (fake / "zenelero.py").write_bytes(b'VERSION = "9.9.9"\r\nx = 1\r\n')
            (fake / "requirements.txt").write_bytes(b"yt-dlp\r\n")
            (fake / "assets" / "icon.png").write_bytes(png)
            (fake / "linux" / "zenelero.desktop").write_bytes(b"[Desktop Entry]\r\nExec=@EXEC@\r\n")
            with mock.patch.object(build_linux, "ROOT", fake), \
                    mock.patch.object(build_linux, "DATA_FILES", ["requirements.txt", "assets/icon.png"]), \
                    mock.patch.object(build_linux, "SCRIPTS", {}):
                target = build_linux.build(Path(out))
            with tarfile.open(target) as tar:
                data = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
        self.assertEqual(data["zenelero-9.9.9/zenelero.py"], b'VERSION = "9.9.9"\nx = 1\n')
        self.assertEqual(data["zenelero-9.9.9/requirements.txt"], b"yt-dlp\n")
        self.assertEqual(data["zenelero-9.9.9/zenelero.desktop"], b"[Desktop Entry]\nExec=@EXEC@\n")
        self.assertEqual(data["zenelero-9.9.9/assets/icon.png"], png)

    def test_a_build_leall_a_hianyzo_helyi_importnal(self):
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as src:
            fake = Path(src)
            (fake / "zenelero.py").write_text('VERSION = "9.9.9"\nimport csak_a_forrasban\n', encoding="utf-8")
            (fake / "csak_a_forrasban.py").write_text("x = 1\n", encoding="utf-8")
            with mock.patch.object(build_linux, "ROOT", fake), \
                    mock.patch.object(build_linux, "EXCLUDE", build_linux.EXCLUDE | {"csak_a_forrasban.py"}), \
                    mock.patch.object(build_linux, "DATA_FILES", []), \
                    mock.patch.object(build_linux, "SCRIPTS", {}):
                with self.assertRaises(SystemExit) as raised:
                    build_linux.build(Path(out))
        self.assertIn("csak_a_forrasban", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
