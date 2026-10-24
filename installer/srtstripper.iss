; srtstripper Windows installer, per-user, no elevation.
; Build with installer/build-installers.ps1 (passes AppVersion, Arch, DistDir, OutDir).
; The two setups share one AppId so an architecture switch upgrades in place.

#define AppName "srtstripper"
#define AppPublisher "westercoder"
#define AppUrl "https://github.com/chezhenkie/srt-subtitle-stripper"
#define RepoRoot AddBackslash(SourcePath) + ".."

#ifndef AppVersion
  #error AppVersion define is required
#endif

#ifndef Arch
  #error Arch define is required
#endif

#if Arch == "x86_64"
  #define SourceExe "srtstripper-windows-x86_64.exe"
  #define ArchAllowed "x64compatible and not arm64"
#elif Arch == "aarch64"
  #define SourceExe "srtstripper-windows-aarch64.exe"
  #define ArchAllowed "arm64"
#else
  #error Unsupported Arch value
#endif

#ifndef DistDir
  #error DistDir define is required
#endif

#ifndef OutDir
  #error OutDir define is required
#endif

[Setup]
AppId={{40F9FA3F-B2AD-49E1-BD44-7A7BD5CBD3C1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
AppCopyright=Copyright (c) 2026 westercoder (MIT License)
DefaultDirName={localappdata}\Programs\srtstripper
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed={#ArchAllowed}
OutputDir={#OutDir}
OutputBaseFilename=srtstripper-windows-{#Arch}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\srtstripper.exe
UninstallDisplayName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}.0

[Files]
Source: "{#DistDir}\{#SourceExe}"; DestDir: "{app}"; DestName: "srtstripper.exe"; Flags: ignoreversion
Source: "{#RepoRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\srtstripper"; Filename: "{app}\srtstripper.exe"; Comment: "Strip non-alphabetic lines from SRT/text files"
Name: "{userprograms}\Uninstall srtstripper"; Filename: "{uninstallexe}"; Comment: "Uninstall srtstripper"

[Tasks]
Name: "addpath"; Description: "Add srtstripper to the user PATH"; GroupDescription: "Environment:"; Flags: checkedonce

[Code]
const
  EnvKey = 'Environment';
  MarkerKey = 'Software\srtstripper';
  WM_SETTINGCHANGE = $001A;
  SMTO_ABORTIFHUNG = $0002;
  BroadcastHwnd = $FFFF;

function SendMessageTimeout(hWnd: Integer; Msg, wParam: Cardinal; lParam: String;
  fuFlags, uTimeout: Cardinal; var lpdwResult: Cardinal): Integer;
  external 'SendMessageTimeoutW@user32.dll stdcall';

procedure NotifyEnvironmentChange;
var
  Res: Cardinal;
begin
  SendMessageTimeout(BroadcastHwnd, WM_SETTINGCHANGE, 0, 'Environment',
    SMTO_ABORTIFHUNG, 5000, Res);
end;

function CanonicalEntry(const S: String): String;
begin
  Result := Trim(S);
  if (Length(Result) >= 2) and (Result[1] = '"') and
     (Result[Length(Result)] = '"') then
    Result := Copy(Result, 2, Length(Result) - 2);
  while (Length(Result) > 0) and (Result[Length(Result)] = '\') do
    Delete(Result, Length(Result), 1);
  Result := Uppercase(Result);
end;

function TryReadUserPath(var Value: String; var HasValue: Boolean): Boolean;
begin
  Value := '';
  HasValue := RegQueryStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', Value);
  { A missing value is fine; an unreadable one means the PATH is left alone. }
  Result := HasValue or (not RegValueExists(HKEY_CURRENT_USER, EnvKey, 'Path'));
end;

{ Set only when this setup added the install dir to PATH, so an uninstall that
  never added it (for example with /TASKS=) cannot remove it. }
function PathMarkerExists: Boolean;
begin
  Result := RegValueExists(HKEY_CURRENT_USER, MarkerKey, 'PathAdded');
end;

function ListHasEntry(const List, Entry: String): Boolean;
var
  Rest, Item: String;
  P: Integer;
begin
  Result := False;
  Rest := List;
  while Rest <> '' do
  begin
    P := Pos(';', Rest);
    if P = 0 then
    begin
      Item := Rest;
      Rest := '';
    end
    else
    begin
      Item := Copy(Rest, 1, P - 1);
      Rest := Copy(Rest, P + 1, Length(Rest) - P);
    end;
    if CanonicalEntry(Item) = CanonicalEntry(Entry) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function RemoveEntry(const List, Entry: String): String;
var
  Rest, Item, Acc: String;
  P: Integer;
  First: Boolean;
begin
  Acc := '';
  First := True;
  Rest := List;
  while True do
  begin
    P := Pos(';', Rest);
    if P = 0 then
    begin
      Item := Rest;
      Rest := '';
    end
    else
    begin
      Item := Copy(Rest, 1, P - 1);
      Rest := Copy(Rest, P + 1, Length(Rest) - P);
    end;
    if CanonicalEntry(Item) <> CanonicalEntry(Entry) then
    begin
      if not First then
        Acc := Acc + ';';
      Acc := Acc + Item;
      First := False;
    end;
    if P = 0 then
      Break;
  end;
  Result := Acc;
end;

procedure AddToUserPath;
var
  Entry, Current: String;
  HasValue: Boolean;
begin
  Entry := ExpandConstant('{app}');
  if not TryReadUserPath(Current, HasValue) then
  begin
    Log('Cannot read the user PATH; leaving it unchanged');
    Exit;
  end;
  if HasValue and ListHasEntry(Current, Entry) then
  begin
    Log('PATH already contains ' + Entry);
    Exit;
  end;
  if Trim(Current) = '' then
    RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', Entry)
  else
    { Append, never replace: an existing trailing separator is an empty entry
      that must survive, so add/remove round-trips byte-exact. }
    RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', Current + ';' + Entry);
  RegWriteDWordValue(HKEY_CURRENT_USER, MarkerKey, 'PathAdded', 1);
  Log('PATH entry added: ' + Entry);
  NotifyEnvironmentChange;
end;

procedure RemoveFromUserPath;
var
  Entry, Current, Updated: String;
  HasValue: Boolean;
begin
  Entry := ExpandConstant('{app}');
  if not PathMarkerExists then
  begin
    Log('The PATH entry was not added by this installer; leaving it unchanged');
    Exit;
  end;
  if not TryReadUserPath(Current, HasValue) then
  begin
    Log('Cannot read the user PATH; leaving it unchanged');
    Exit;
  end;
  if (not HasValue) or (not ListHasEntry(Current, Entry)) then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, MarkerKey, 'PathAdded');
    Log('PATH does not contain ' + Entry);
    Exit;
  end;
  Updated := RemoveEntry(Current, Entry);
  RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvKey, 'Path', Updated);
  RegDeleteValue(HKEY_CURRENT_USER, MarkerKey, 'PathAdded');
  Log('PATH entry removed: ' + Entry);
  NotifyEnvironmentChange;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addpath') then
    AddToUserPath;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromUserPath;
end;
