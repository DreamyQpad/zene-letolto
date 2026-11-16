"""A Linuxos platformréteg viselkedését rögzítő tesztek: minden operációs rendszeren futnak,
a külső hívásokat (folyamatindítás, jelküldés, which) mockok helyettesítik."""
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import plat_linux  # noqa: E402
from plat_linux import (  # noqa: E402
    CREATE_NO_WINDOW, FFMPEG_EXE, FROZEN, LOG_FONT, PY, child_env, config_dir, find_ffmpeg_dir,
    fix_stdio, hide_child_windows, kill_tree, open_folder, reveal, set_window_icon, spawn_kwargs,
    spotdl_cmd, spotlist_cmd, ytdlp_cmd,
)

SIGKILL = 9
HUNGARIAN_NAME = "Árvíztűrő tükörfúrógép dal.mp3"


class ConfigDirTest(unittest.TestCase):
    def test_az_xdg_config_home_erteket_hasznalja(self):
        self.assertEqual(config_dir({"XDG_CONFIG_HOME": "/x/cfg"}), Path("/x/cfg") / "zenelero")

    def test_ures_hianyzo_vagy_relativ_ertek_eseten_az_alapertelmezett(self):
        for env in ({}, {"XDG_CONFIG_HOME": ""}, {"XDG_CONFIG_HOME": "relativ/ut"}):
            with self.subTest(env=env):
                self.assertEqual(config_dir(env), Path.home() / ".config" / "zenelero")

    def test_a_user_bin_az_adatmappa_bin_almappaja(self):
        self.assertEqual(plat_linux.USER_BIN, plat_linux.DATA_DIR / "bin")


class ConstantsAndCommandsTest(unittest.TestCase):
    def test_allandok(self):
        self.assertEqual((FROZEN, CREATE_NO_WINDOW, FFMPEG_EXE, LOG_FONT), (False, 0, "ffmpeg", "monospace"))
        self.assertEqual(PY, Path(sys.executable))

    def test_eszkozparancsok(self):
        self.assertEqual(ytdlp_cmd(), [sys.executable, "-m", "yt_dlp"])
        self.assertEqual(spotdl_cmd(), [sys.executable, "-m", "spotdl"])
        self.assertEqual(spotlist_cmd("https://open.spotify.com/x"),
                         [sys.executable, str(plat_linux.HERE / "spotify_list.py"), "https://open.spotify.com/x"])

    def test_spawn_kwargs_uj_session(self):
        self.assertEqual(spawn_kwargs(), {"start_new_session": True})

    def test_find_ffmpeg_dir(self):
        with mock.patch.object(plat_linux.shutil, "which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(find_ffmpeg_dir(), str(Path("/usr/bin/ffmpeg").parent))
        with mock.patch.object(plat_linux.shutil, "which", return_value=None):
            self.assertIsNone(find_ffmpeg_dir())

    def test_child_env_masolat(self):
        env = child_env()
        env["X_PROBA"] = "1"
        self.assertNotIn("X_PROBA", os.environ)

    def test_nincs_ablakrejtes(self):
        init = subprocess.Popen.__init__
        self.assertIsNone(hide_child_windows())
        self.assertIsNone(fix_stdio())
        self.assertIs(subprocess.Popen.__init__, init)


class KillTreeTest(unittest.TestCase):
    def test_kilepett_folyamatnal_nincs_jelkuldes(self):
        proc = mock.Mock(pid=4242)
        proc.poll.return_value = 0
        with mock.patch.object(os, "killpg", create=True) as killpg, \
                mock.patch.object(plat_linux.threading, "Timer") as timer:
            kill_tree(proc)
        killpg.assert_not_called()
        timer.assert_not_called()

    def test_nincs_folyamat_nincs_hiba(self):
        with mock.patch.object(os, "killpg", create=True) as killpg:
            kill_tree(None)
        killpg.assert_not_called()

    def test_sigterm_majd_sigkill_a_halasztott_idozitovel(self):
        proc = mock.Mock(pid=4242)
        proc.poll.return_value = None
        killed = threading.Event()
        with mock.patch.object(os, "killpg", create=True) as killpg:
            killpg.side_effect = lambda pgid, sig: killed.set() if sig == SIGKILL else None
            kill_tree(proc, grace=0.05)
            self.assertEqual(killpg.call_args_list[0], mock.call(4242, signal.SIGTERM))
            self.assertTrue(killed.wait(2), "a SIGKILL nem érkezett meg a türelmi idő után")
        self.assertEqual(killpg.call_args_list, [mock.call(4242, signal.SIGTERM), mock.call(4242, SIGKILL)])

    def test_a_hivas_nem_var_a_turelmi_idore(self):
        proc = mock.Mock(pid=4242)
        proc.poll.return_value = None
        with mock.patch.object(os, "killpg", create=True) as killpg, \
                mock.patch.object(plat_linux.threading, "Timer") as timer:
            kill_tree(proc)
        killpg.assert_called_once_with(4242, signal.SIGTERM)
        timer.assert_called_once()
        self.assertIs(timer.return_value.daemon, True)
        timer.return_value.start.assert_called_once_with()

    def test_eltunt_csoport_nem_dob_kivetelt(self):
        proc = mock.Mock(pid=4242)
        proc.poll.return_value = None
        with mock.patch.object(os, "killpg", create=True, side_effect=ProcessLookupError) as killpg, \
                mock.patch.object(plat_linux.threading, "Timer") as timer:
            kill_tree(proc)
            killpg.assert_called_once_with(4242, signal.SIGTERM)
            killer = timer.call_args.args[1]
            killer()    # a halasztott SIGKILL is elnyeli a hiányzó csoportot
        self.assertEqual(killpg.call_args_list[-1], mock.call(4242, SIGKILL))

    def test_a_sigkill_a_vezerfolyamat_kilepese_utan_is_megy(self):
        """A vezér SIGTERM-re kilép, de a csoport többi tagja élhet: a SIGKILL ilyenkor is jár a csoportnak."""
        proc = mock.Mock(pid=4242)
        proc.poll.return_value = None
        with mock.patch.object(os, "killpg", create=True) as killpg, \
                mock.patch.object(plat_linux.threading, "Timer") as timer:
            kill_tree(proc)
            proc.poll.return_value = 0
            timer.call_args.args[1]()
        self.assertEqual(killpg.call_args_list, [mock.call(4242, signal.SIGTERM), mock.call(4242, SIGKILL)])


class RevealTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.file = self.folder / HUNGARIAN_NAME
        self.file.write_bytes(b"")

    def launched(self, files, folder, dolphin=True):
        which = "/usr/bin/dolphin" if dolphin else None
        with mock.patch.object(plat_linux.shutil, "which", return_value=which), \
                mock.patch.object(plat_linux.subprocess, "Popen") as popen:
            reveal(files, folder)
        return popen

    def test_dolphin_a_fajlt_jeloli_ki_szokozos_ekezetes_nevvel_is(self):
        popen = self.launched([str(self.file)], str(self.folder))
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["dolphin", "--select", str(self.file)])
        self.assertEqual(popen.call_args.kwargs, {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                                                  "start_new_session": True})

    def test_dolphin_nelkul_a_fajl_mappaja_nyilik_meg(self):
        popen = self.launched([str(self.file)], str(self.folder), dolphin=False)
        self.assertEqual(popen.call_args.args[0], ["xdg-open", str(self.file.parent)])

    def test_csak_mappa_eseten_xdg_open_a_mappara(self):
        popen = self.launched([], str(self.folder))
        self.assertEqual(popen.call_args.args[0], ["xdg-open", str(self.folder)])

    def test_nemletezo_fajl_eseten_a_mappa_nyilik_meg(self):
        popen = self.launched([str(self.folder / "nincs.mp3")], str(self.folder))
        self.assertEqual(popen.call_args.args[0], ["xdg-open", str(self.folder)])

    def test_az_elso_letezo_fajl_szamit(self):
        popen = self.launched([str(self.folder / "nincs.mp3"), str(self.file)], str(self.folder))
        self.assertEqual(popen.call_args.args[0], ["dolphin", "--select", str(self.file)])

    def test_semmi_nem_letezik_nem_indit_es_nem_dob(self):
        missing = self.folder / "nincs"
        for files, folder in (([], str(missing)), ([str(missing / "a.mp3")], str(missing)), ([], None)):
            with self.subTest(files=files, folder=folder):
                self.launched(files, folder).assert_not_called()

    def test_hianyzo_program_nem_dob_kivetelt(self):
        with mock.patch.object(plat_linux.shutil, "which", return_value=None), \
                mock.patch.object(plat_linux.subprocess, "Popen", side_effect=FileNotFoundError):
            reveal([str(self.file)], str(self.folder))
            reveal([], str(self.folder))
            open_folder(self.folder)

    def test_open_folder(self):
        with mock.patch.object(plat_linux.subprocess, "Popen") as popen:
            open_folder(self.folder)
        self.assertEqual(popen.call_args.args[0], ["xdg-open", str(self.folder)])


class WindowIconTest(unittest.TestCase):
    def test_hianyzo_ikonfajl_nem_tesz_semmit(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(plat_linux, "RES_DIR", Path(tmp)):
            root = mock.Mock()
            set_window_icon(root)
        root.after.assert_not_called()

    def test_meglevo_ikon_kesleltetve_kerul_fel_es_a_kepre_marad_referencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "assets" / "icon.png"
            icon.parent.mkdir()
            icon.write_bytes(b"")
            root = mock.Mock()
            with mock.patch.object(plat_linux, "RES_DIR", Path(tmp)), \
                    mock.patch("tkinter.PhotoImage") as photo:
                set_window_icon(root)
                self.assertEqual(root.after.call_args.args[0], 300)
                root.after.call_args.args[1]()
            photo.assert_called_once_with(file=str(icon))
            root.iconphoto.assert_called_once_with(True, photo.return_value)
            self.assertIn(photo.return_value, vars(root).values())


if __name__ == "__main__":
    unittest.main()
