; Zene letöltő telepítő (Inno Setup 6). Fordítás: ISCC.exe telepito.iss
; Előfeltétel: build_installer\dist\ZeneLetolto\ kész (PyInstaller) és benne a bin\ffmpeg.exe + bin\deno.exe.

#define AppName "Zene letöltő"
#define AppVersion "1.0"
#define AppExe "ZeneLetolto.exe"

[Setup]
AppId={{7C1D5B7E-3F0A-4D8B-9C52-5A8E6B1F2D44}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; felhasználói telepítés (nem kér rendszergazdát); a varázslóban át lehet váltani minden felhasználóra
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\out
OutputBaseFilename=Zene-letolto-telepito
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UsePreviousAppDir=yes
CloseApplications=yes

[Languages]
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"

[Tasks]
Name: "desktopicon"; Description: "Asztali parancsikon létrehozása"; GroupDescription: "További parancsikonok:"

[Files]
Source: "dist\ZeneLetolto\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Zene letöltő indítása"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; a Frissítéssel letöltött yt-dlp.exe a felhasználói adatmappában van
Type: filesandordirs; Name: "{userappdata}\{#AppName}\bin"
