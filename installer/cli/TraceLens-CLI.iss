; Inno Setup script for TraceLens CLI (standalone Windows installer)
; Prerequisite: Build the PyInstaller CLI onedir bundle first:
;   pyinstaller --noconfirm --clean --distpath dist/v2/cli --workpath build/cli packaging/TraceLens-cli.spec

#define MyAppName "TraceLens CLI"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "TraceLens"
#define MyAppURL "https://github.com/Tanmay-Bhatnagar22/TraceLens"
#define MyAppExeName "TraceLens.exe"

[Setup]
AppId={{B4C9E217-6D3A-4E8B-9F12-7A5C3D8E1B40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\TraceLens-CLI
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
ChangesEnvironment=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\v2\installer
OutputBaseFilename=TraceLens-CLI-Setup
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
Name: "addtopath"; Description: "Add TraceLens CLI to your user PATH (recommended for Command Prompt / PowerShell)"; GroupDescription: "Environment:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\v2\cli\TraceLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{cmd}"; Parameters: "/k """"{app}\{#MyAppExeName}"" --help"""; WorkingDir: "{userdocs}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{cmd}"; Parameters: "/k """"{app}\{#MyAppExeName}"" --help"""; WorkingDir: "{userdocs}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Code]
const
  EnvKey = 'Environment';
  PathMarkerFile = 'tracelens_path_added.txt';

function NormalizeDir(const S: String): String;
begin
  Result := RemoveBackslashUnlessRoot(Trim(S));
end;

function PathContainsDir(const PathValue, TargetDir: String): Boolean;
var
  Remaining, Segment, NormTarget: String;
  P: Integer;
begin
  Result := False;
  NormTarget := NormalizeDir(TargetDir);
  Remaining := PathValue;
  while Remaining <> '' do
  begin
    P := Pos(';', Remaining);
    if P > 0 then
    begin
      Segment := Copy(Remaining, 1, P - 1);
      Delete(Remaining, 1, P);
    end
    else
    begin
      Segment := Remaining;
      Remaining := '';
    end;
    if (Segment <> '') and (CompareText(NormalizeDir(Segment), NormTarget) = 0) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

procedure AddDirToUserPath(const DirToAdd: String);
var
  OrigPath, NewPath, MarkerPath: String;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', OrigPath) then
    OrigPath := '';

  if PathContainsDir(OrigPath, DirToAdd) then
    Exit;

  if OrigPath = '' then
    NewPath := DirToAdd
  else if OrigPath[Length(OrigPath)] = ';' then
    NewPath := OrigPath + DirToAdd
  else
    NewPath := OrigPath + ';' + DirToAdd;

  if RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', NewPath) then
  begin
    MarkerPath := ExpandConstant('{app}\') + PathMarkerFile;
    SaveStringToFile(MarkerPath, DirToAdd, False);
  end;
end;

procedure RemoveDirFromUserPath(const DirToRemove: String);
var
  OrigPath, Remaining, Segment, OutPath, NormTarget: String;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', OrigPath) then
    Exit;

  NormTarget := NormalizeDir(DirToRemove);
  OutPath := '';
  Remaining := OrigPath;

  while Remaining <> '' do
  begin
    P := Pos(';', Remaining);
    if P > 0 then
    begin
      Segment := Copy(Remaining, 1, P - 1);
      Delete(Remaining, 1, P);
    end
    else
    begin
      Segment := Remaining;
      Remaining := '';
    end;

    Segment := Trim(Segment);
    if (Segment <> '') and (CompareText(NormalizeDir(Segment), NormTarget) <> 0) then
    begin
      if OutPath = '' then
        OutPath := Segment
      else
        OutPath := OutPath + ';' + Segment;
    end;
  end;

  if OutPath = '' then
    RegDeleteValue(HKEY_CURRENT_USER, EnvKey, 'Path')
  else
    RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', OutPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    AddDirToUserPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  MarkerPath, AddedDir: String;
  RawAnsi: AnsiString;
begin
  if CurUninstallStep = usUninstall then
  begin
    MarkerPath := ExpandConstant('{app}\') + PathMarkerFile;
    if FileExists(MarkerPath) then
    begin
      if LoadStringFromFile(MarkerPath, RawAnsi) then
      begin
        AddedDir := String(RawAnsi);
        RemoveDirFromUserPath(AddedDir);
      end
      else
        RemoveDirFromUserPath(ExpandConstant('{app}'));
      DeleteFile(MarkerPath);
    end;
  end;
end;

