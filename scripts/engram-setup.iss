; Engram — Inno Setup Installer Script
; Requires: Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
;
; Usage:
;   1. Run build_windows.bat first (creates dist\installer\)
;   2. Open this file in Inno Setup Compiler
;   3. Click Build → Compile
;   4. Output: dist\Engram-Setup-0.1.0.exe

#define AppName "Engram"
#define AppVersion "0.1.0"
#define AppPublisher "Engram Contributors"
#define AppURL "https://github.com/ReliOptic/engram"

[Setup]
AppId={{B8F3D2A1-7E4C-4A9B-8D6F-1C2E5A3B9D7F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Engram-Setup-{#AppVersion}
SetupIconFile=engram.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\engram\engram.exe
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Types]
Name: "full"; Description: "Full installation (Engram + DB Builder)"
Name: "server"; Description: "Engram server only"
Name: "dbbuilder"; Description: "DB Builder only"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "main"; Description: "Engram — Multi-Agent Support System"; Types: full server; Flags: fixed
Name: "dbbuilder"; Description: "Engram DB Builder — Knowledge Base Builder"; Types: full dbbuilder

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "desktopicon\engram"; Description: "Engram"; Components: main
Name: "desktopicon\dbbuilder"; Description: "Engram DB Builder"; Components: dbbuilder

[Files]
; Main Engram server
Source: "..\dist\installer\engram\*"; DestDir: "{app}\engram"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs

; DB Builder
Source: "..\dist\installer\engram-db-builder\*"; DestDir: "{app}\engram-db-builder"; Components: dbbuilder; Flags: ignoreversion recursesubdirs createallsubdirs

; Shared
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

; Data directories (empty, user fills later)
Source: "..\data\config\*"; DestDir: "{app}\data\config"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

; .env template
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env.example"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Dirs]
Name: "{app}\data\chroma_db"; Components: main
Name: "{app}\data\sqlite"; Components: main
Name: "{app}\data\uploads"; Components: main
Name: "{app}\data\raw\manuals"; Components: dbbuilder
Name: "{app}\data\raw\weekly_reports"; Components: main
Name: "{app}\data\raw\sops"; Components: dbbuilder

[Icons]
; Start Menu
Name: "{group}\Engram"; Filename: "{app}\engram\engram.exe"; WorkingDir: "{app}"; Components: main; Comment: "Start Engram server"
Name: "{group}\Engram DB Builder"; Filename: "{app}\engram-db-builder\engram-db-builder.exe"; WorkingDir: "{app}"; Components: dbbuilder; Comment: "Launch DB Builder"
Name: "{group}\Edit Configuration"; Filename: "notepad.exe"; Parameters: """{app}\.env"""; Components: main
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"

; Desktop
Name: "{autodesktop}\Engram"; Filename: "{app}\engram\engram.exe"; WorkingDir: "{app}"; Components: main; Tasks: desktopicon\engram; IconFilename: "{app}\engram\engram.exe"
Name: "{autodesktop}\Engram DB Builder"; Filename: "{app}\engram-db-builder\engram-db-builder.exe"; WorkingDir: "{app}"; Components: dbbuilder; Tasks: desktopicon\dbbuilder

[Run]
Filename: "{app}\engram\engram.exe"; Description: "Launch Engram now"; Flags: nowait postinstall skipifsilent; Components: main

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data\chroma_db"
Type: filesandordirs; Name: "{app}\data\sqlite"
Type: filesandordirs; Name: "{app}\data\uploads"
Type: files; Name: "{app}\.env"

[Code]
// Show a welcome page with description
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvFile: String;
begin
  // After install, ensure .env exists
  if CurStep = ssPostInstall then
  begin
    EnvFile := ExpandConstant('{app}\.env');
    if not FileExists(EnvFile) then
      FileCopy(ExpandConstant('{app}\.env.example'), EnvFile, True);
  end;
end;
