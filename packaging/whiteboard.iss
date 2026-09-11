#ifndef AppVersion
  #define AppVersion "0.1.2"
#endif
#ifndef SourceRoot
  #define SourceRoot ".."
#endif

#define AppName "WhiteBoard"
#define AppPublisher "WhiteBoard"

[Setup]
AppId={{8F3C1A62-4B7D-4E9A-A1C5-9D2E6B7A4C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#SourceRoot}\dist
OutputBaseFilename={#AppName}-Setup
SetupIconFile={#SourceRoot}\assets\logo.ico
UninstallDisplayIcon={app}\{#AppName}.exe
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UsePreviousAppDir=yes
UsePreviousTasks=yes
CloseApplications=yes
RestartApplications=no
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
AllowNoIcons=yes
ChangesEnvironment=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "{#SourceRoot}\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\packaging\installed-by-setup.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; WorkingDir: "{app}"; Comment: "{#AppName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; WorkingDir: "{app}"; Comment: "{#AppName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\installed-by-setup.txt"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  { Close any running WhiteBoard.exe so the previous copy can be replaced. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM WhiteBoard.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
