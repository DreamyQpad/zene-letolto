# Telepito ujraepitese: powershell -ExecutionPolicy Bypass -File build.ps1
# 1) PyInstaller csomag  2) ffmpeg+deno bemasolasa (build_installer\bin-src)  3) Inno Setup -> out\Zene-letolto-telepito.exe
$ErrorActionPreference = 'Continue'   # a PyInstaller az allapotuzeneteit a hibacsatornan irja, ez nem hiba
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "$root\.venv\Scripts\python.exe"
$b = "$root\build_installer"
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

& $py -m PyInstaller --noconfirm --clean --onedir --noconsole --name ZeneLetolto --icon "$root\assets\icon.ico" `
  --distpath "$b\dist" --workpath "$b\work" --specpath "$b" --paths $root `
  --add-data "$root\assets;assets" --hidden-import spotify_list `
  --collect-all customtkinter --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all spotdl `
  --collect-all ytmusicapi --collect-all pykakasi --collect-all syncedlyrics --collect-all spotipy `
  --collect-all spotipyfree --collect-all soundcloud_v2 --collect-all slugify --collect-all rapidfuzz `
  --collect-all certifi --collect-all datastar_py --collect-all uvicorn --collect-all fastapi `
  "$root\zenelero.py" *> "$b\pyinstaller.log"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller hiba, lasd: $b\pyinstaller.log" }

New-Item -ItemType Directory -Force "$b\dist\ZeneLetolto\bin" | Out-Null
Copy-Item "$b\bin-src\*.exe" "$b\dist\ZeneLetolto\bin" -Force

if (-not (Test-Path $iscc)) { throw 'Nincs Inno Setup: winget install --id JRSoftware.InnoSetup' }
Set-Location $b
& $iscc /Q "$b\telepito.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup hiba" }
# mindig keszul egy masolat a Dokumentumok\telepitok mappaba is
$docs = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'telepitok'
New-Item -ItemType Directory -Force $docs | Out-Null
Copy-Item "$root\out\Zene-letolto-telepito.exe" $docs -Force
"Kesz: $root\out\Zene-letolto-telepito.exe"
"Masolat: $docs\Zene-letolto-telepito.exe"


