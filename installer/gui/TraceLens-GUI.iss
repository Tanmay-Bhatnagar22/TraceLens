; Inno Setup script for TraceLens GUI (standalone Windows installer)
; Prerequisite: Build the PyInstaller onedir bundle first:
;   pyinstaller --noconfirm --clean --distpath dist/v2 --workpath build packaging/TraceLens.spec

#define MyAppName "TraceLens GUI"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "TraceLens"
#define MyAppURL "https://github.com/Tanmay-Bhatnagar22/TraceLens"
#define MyAppExeName "TraceLens.exe"

[Setup]
AppId={{8E7B4F2A-3C9D-4A1E-9B6F-2D5C1A8E7F02}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\TraceLens
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\v2\installer
OutputBaseFilename=TraceLens-GUI-Setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\assets\Metadata.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\v2\TraceLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

