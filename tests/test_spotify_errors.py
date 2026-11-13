"""Nem elérhető Spotify-szám: érthető hibaüzenet, és a csomagolt eszköz ne dobjon fel Python-hibaablakot."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import zenelero  # noqa: E402

# A SpotipyFree így száll el, ha a Spotify nem ad vissza adatot a számhoz (törölt / nem elérhető / érvénytelen azonosító)
TRACEBACK = '''Traceback (most recent call last):
  File "spotify_list.py", line 26, in <module>
  File "spotdl\types\song.py", line 86, in from_url
    raw_track_meta = spotify_client.track(url)
  File "SpotipyFree\Spotify.py", line 329, in track
  File "SpotipyFree\Formatter.py", line 40, in formatTrack
KeyError: 'uri'
'''


def failed(stderr=TRACEBACK):
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


class SpotifyErrorTest(unittest.TestCase):
    def test_a_spotify_keyerror_erthető_magyarazatot_kap(self):
        hint = zenelero.hint_for(TRACEBACK)
        self.assertIsNotNone(hint)
        self.assertIn("Spotify", hint)

    def test_nem_elerheto_szamnal_erthetoen_hibazik_es_nem_probalja_a_tartalekot(self):
        with mock.patch.object(zenelero.subprocess, "run", return_value=failed()) as run:
            with self.assertRaises(RuntimeError) as cm:
                zenelero.spotify_info("https://open.spotify.com/track/0000000000000000000000")
        self.assertIn("Spotify", str(cm.exception))
        self.assertNotIn("Expecting value", str(cm.exception))        # nem nyers JSON-hiba
        self.assertEqual(run.call_count, 1)                           # a `spotdl save` ugyanígy elbukna, felesleges

    def test_a_csomagolt_eszkoz_kezeletlen_kivetel_helyett_hibakoddal_lep_ki(self):
        with mock.patch("yt_dlp.main", side_effect=KeyError("uri")), \
                mock.patch.object(sys, "stderr", new=mock.MagicMock()):
            with self.assertRaises(SystemExit) as cm:
                zenelero.tool_main("yt-dlp", ["x"])
        self.assertEqual(cm.exception.code, 1)

    def test_mukodo_link_tovabbra_is_adatot_ad(self):
        data = {"kind": "track", "name": "N", "cover": None,
                "songs": [{"url": "u", "artist": "A", "name": "N", "duration": 10}]}
        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="JSON:" + json.dumps(data) + "\n", stderr="")
        with mock.patch.object(zenelero.subprocess, "run", return_value=ok):
            self.assertEqual(zenelero.spotify_info("https://open.spotify.com/track/x")["name"], "N")


if __name__ == "__main__":
    unittest.main()
