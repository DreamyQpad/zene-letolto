"""A csomagolt (konzol nélküli) eszköz gyerekfolyamatai (deno, ffmpeg, ffprobe) ne nyissanak konzolablakot."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import plat  # noqa: E402
import zenelero  # noqa: E402

PYTHONW = zenelero.PY.with_name("pythonw.exe")

# Konzol nélküli szülőből indított konzolos gyerek: van-e látható konzolablaka?
PARENT = r'''
import asyncio, os, subprocess, sys
sys.path.insert(0, {root!r})
if {patch!r}:
    import zenelero
    zenelero.hide_child_windows()
child = "import ctypes;print(bool(ctypes.windll.kernel32.GetConsoleWindow()))"


async def via_asyncio():
    p = await asyncio.create_subprocess_exec({py!r}, "-c", child, stdout=asyncio.subprocess.PIPE)
    return (await p.communicate())[0].decode().strip()


popen = subprocess.run([{py!r}, "-c", child], capture_output=True, text=True).stdout.strip()
aio = asyncio.run(via_asyncio())
os.system('""' + {py!r} + '" -c "' + child + '" > "' + {result!r} + '.system""')
os.system("")        # a spotapi így kapcsolja be a konzol színeit, importáláskor
open({result!r}, "w").write(",".join([popen, aio, open({result!r} + ".system").read().strip()]))
'''


class Recorded(Exception):
    pass


class HideChildWindowsTest(unittest.TestCase):
    def setUp(self):
        self._orig = subprocess.Popen.__init__
        self.addCleanup(setattr, subprocess.Popen, "__init__", self._orig)
        self.seen = {}

        def recorder(inner, args, *a, **kw):
            self.seen["flags"] = kw.get("creationflags", 0)
            raise Recorded

        subprocess.Popen.__init__ = recorder

    def launch(self, **kw):
        with self.assertRaises(Recorded):
            subprocess.Popen(["nincs-ilyen-program"], **kw)
        return self.seen["flags"]

    def test_a_gyerekfolyamat_alapbol_ablak_nelkul_indul(self):
        zenelero.hide_child_windows()
        self.assertTrue(self.launch() & plat.CREATE_NO_WINDOW)

    def test_a_kifejezetten_kert_flag_megmarad(self):
        zenelero.hide_child_windows()
        flags = self.launch(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.assertTrue(flags & subprocess.CREATE_NEW_PROCESS_GROUP)
        self.assertTrue(flags & plat.CREATE_NO_WINDOW)

    def test_ketszeri_hivas_nem_halmozza_a_burkolast(self):
        zenelero.hide_child_windows()
        wrapped = subprocess.Popen.__init__
        zenelero.hide_child_windows()
        self.assertIs(subprocess.Popen.__init__, wrapped)

    def test_az_os_system_is_ablak_nelkul_indul(self):
        self.addCleanup(setattr, os, "system", os.system)
        zenelero.hide_child_windows()
        with self.assertRaises(Recorded):
            os.system("echo szia")
        self.assertTrue(self.seen["flags"] & plat.CREATE_NO_WINDOW)

    def test_az_ures_os_system_nem_indit_semmit(self):
        """A spotapi importáláskor os.system("")-ot hív (konzolszín-trükk): ablak nélküli exe-ben ez
        felesleges, és új konzolablakot nyitna."""
        self.addCleanup(setattr, os, "system", os.system)
        zenelero.hide_child_windows()
        self.assertEqual(os.system(""), 0)
        self.assertNotIn("flags", self.seen)

    def test_az_os_system_visszateresi_erteke_megmarad(self):
        self.addCleanup(setattr, os, "system", os.system)
        subprocess.Popen.__init__ = self._orig
        zenelero.hide_child_windows()
        self.assertEqual(os.system("exit 3"), 3)

    def test_a_yt_dlp_popenje_is_ablak_nelkul_indul(self):
        from yt_dlp.utils import Popen as YtPopen
        zenelero.hide_child_windows()
        with self.assertRaises(Recorded):
            YtPopen(["nincs-ilyen-program"])
        self.assertTrue(self.seen["flags"] & plat.CREATE_NO_WINDOW)


@unittest.skipUnless(sys.platform == "win32" and PYTHONW.is_file(), "csak Windowson, a .venv pythonw.exe-vel")
class ConsolelessParentTest(unittest.TestCase):
    def child_console_windows(self, patch):
        """"van konzolablak" a subprocess.Popen-nel és az asyncio-val (spotDL ffmpeg) indított gyereknek."""
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "result.txt"
            script = Path(tmp) / "parent.py"
            script.write_text(PARENT.format(root=str(zenelero.HERE), patch=patch, py=str(zenelero.PY),
                                            result=str(result)), encoding="utf-8")
            subprocess.run([str(PYTHONW), str(script)], timeout=60, check=True)
            return result.read_text()

    def test_javitas_nelkul_a_gyerek_konzolablakot_kap(self):
        self.assertEqual(self.child_console_windows(patch=False), "True,True,True")

    def test_javitassal_a_gyerek_nem_kap_konzolablakot(self):
        self.assertEqual(self.child_console_windows(patch=True), "False,False,False")


if __name__ == "__main__":
    unittest.main()
