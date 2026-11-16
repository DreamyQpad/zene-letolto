"""A Windowsos platformréteg viselkedését rögzítő tesztek."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

if sys.platform == "win32":
    import plat
    import plat_windows


@unittest.skipUnless(sys.platform == "win32", "csak Windowson")
class PlatWindowsTest(unittest.TestCase):
    def test_spawn_kwargs_ablak_nelkul(self):
        self.assertEqual(plat_windows.spawn_kwargs(), {"creationflags": 0x08000000})

    def test_nevek(self):
        self.assertEqual((plat_windows.FFMPEG_EXE, plat_windows.LOG_FONT), ("ffmpeg.exe", "Consolas"))

    def test_fejlesztoi_eszkozparancsok(self):
        """Nem csomagolt futásnál a .venv Pythonja indítja az eszközöket."""
        self.assertFalse(plat_windows.FROZEN)
        self.assertEqual(plat_windows.ytdlp_cmd(), [str(plat_windows.PY), "-m", "yt_dlp"])
        self.assertEqual(plat_windows.spotdl_cmd(), [str(plat_windows.PY), "-m", "spotdl"])
        self.assertEqual(plat_windows.spotlist_cmd("U")[-2:], [str(HERE / "spotify_list.py"), "U"])

    def test_a_valaszto_windowson_a_windowsos_modult_tolti(self):
        self.assertIs(plat.spawn_kwargs, plat_windows.spawn_kwargs)

    def test_kill_tree_taskkill(self):
        proc = mock.Mock(pid=42)
        proc.poll.return_value = None
        with mock.patch.object(plat_windows.subprocess, "run") as run:
            plat_windows.kill_tree(proc)
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "42", "/T", "/F"])

    def test_kill_tree_kilepett_folyamatot_nem_bant(self):
        proc = mock.Mock(pid=42)
        proc.poll.return_value = 0
        with mock.patch.object(plat_windows.subprocess, "run") as run:
            plat_windows.kill_tree(proc)
        run.assert_not_called()

    def test_open_folder_startfile(self):
        with mock.patch.object(os, "startfile", create=True) as startfile:
            plat_windows.open_folder("C:/valami/mappa")
        startfile.assert_called_once_with("C:/valami/mappa")

    def test_reveal_kijeloli_az_elso_letezo_fajlt(self):
        with tempfile.TemporaryDirectory() as tmp:
            letezo = Path(tmp) / "dal.mp3"
            letezo.write_bytes(b"")
            with mock.patch.object(plat_windows.subprocess, "Popen") as popen:
                plat_windows.reveal([str(Path(tmp) / "nincs.mp3"), str(letezo)], tmp)
        popen.assert_called_once_with(f'explorer /select,"{letezo}"')

    def test_reveal_mappat_nyit_ha_nincs_fajl(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(os, "startfile", create=True) as startfile, \
                    mock.patch.object(plat_windows.subprocess, "Popen") as popen:
                plat_windows.reveal([], tmp)
        popen.assert_not_called()
        startfile.assert_called_once_with(tmp)


if __name__ == "__main__":
    unittest.main()
