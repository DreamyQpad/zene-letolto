"""Spotify szám/album/lista adatainak lekérése YouTube-egyeztetés nélkül (gyors).
Használat: python spotify_list.py <spotify-link>
Kimenet: egy "JSON:" kezdetű sor: {"kind","name","cover","songs":[{"url","artist","name","duration"}]}
A zenelero.py hívja; hiba esetén a régi `spotdl save` módszerre esik vissza.
"""
import json
import sys

from spotdl.utils.config import DEFAULT_CONFIG
from spotdl.utils.spotify import SpotifyClient

url = sys.argv[1]
SpotifyClient.init(client_id=DEFAULT_CONFIG["client_id"], client_secret=DEFAULT_CONFIG["client_secret"],
                   user_auth=False, no_cache=True, headless=True)

if "/playlist/" in url:
    from spotdl.types.playlist import Playlist
    meta, songs = Playlist.get_metadata(url)
    kind, name = "playlist", meta.get("name")
elif "/album/" in url:
    from spotdl.types.album import Album
    meta, songs = Album.get_metadata(url)
    kind, name = "album", meta.get("name")
else:
    from spotdl.types.song import Song
    song = Song.from_url(url)
    songs, kind, name = [song], "track", song.name

print("JSON:" + json.dumps({
    "kind": kind, "name": name,
    "cover": getattr(songs[0], "cover_url", None) if songs else None,
    "songs": [{"url": s.url, "artist": s.artist, "name": s.name, "duration": s.duration} for s in songs],
}))
