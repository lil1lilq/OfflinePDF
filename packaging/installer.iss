; Windows installer for the folder that build_windows.ps1 creates in dist\OfflinePDF.
; build_windows.ps1 passes the version: ISCC /DAppVersion=1.0.0 /DAppVersionNumeric=1.0.0.0
#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z (build_windows.ps1 does this).
#endif
#ifndef AppVersionNumeric
  #define AppVersionNumeric AppVersion + ".0"
#endif
#define AppName "OfflinePDF"

[Setup]
; Keep this AppId: upgrades and uninstalls find earlier installs by it.
AppId={{9DC9CDFB-9463-416E-B5AB-E5E49805C3A7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersionNumeric}
; Staff without administrator rights install for themselves (no UAC prompt).
; IT can install for every user of a PC: setup.exe /ALLUSERS (add /VERYSILENT for silent).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=OfflinePDF-Setup-Windows-x64
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\OfflinePDF.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The same files as the portable ZIP, including licenses and corresponding sources.
Source: "..\dist\OfflinePDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Drop files of an earlier version that this version no longer ships.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\OfflinePDF.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\OfflinePDF.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OfflinePDF.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
