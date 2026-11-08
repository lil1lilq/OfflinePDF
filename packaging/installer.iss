; Windows installer for the folder that build_windows.ps1 creates in dist\OfflinePDF.
; build_windows.ps1 passes the version: ISCC /DAppVersion=1.0.1 /DAppVersionNumeric=1.0.1.0
; (a bug-fix version such as 1.0.0.1 is passed unchanged in both)
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

Name: "explorermenu"; Description: "탐색기 PDF 우클릭 메뉴 추가 / Add Explorer PDF menu"

[Registry]
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF"; Flags: deletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF"; ValueType: string; ValueName: "MUIVerb"; ValueData: "OfflinePDF"; Tasks: explorermenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF"; ValueType: string; ValueName: "SubCommands"; ValueData: ""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick"; ValueType: string; ValueName: "MUIVerb"; ValueData: "바로 실행"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick"; ValueType: string; ValueName: "SubCommands"; ValueData: ""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "PDF 병합"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer merge --quick ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\split"; ValueType: string; ValueName: "MUIVerb"; ValueData: "PDF 분할"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\split"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\split"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\split\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer split --quick ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\compress"; ValueType: string; ValueName: "MUIVerb"; ValueData: "PDF 압축"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\compress"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\compress"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\compress\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer compress --quick ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\upscale"; ValueType: string; ValueName: "MUIVerb"; ValueData: "AI 업스케일"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\upscale"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\upscale"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\upscale\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer upscale --quick ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\unlock"; ValueType: string; ValueName: "MUIVerb"; ValueData: "비밀번호 해제"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\unlock"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\unlock"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\unlock\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer unlock --quick ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\protect"; ValueType: string; ValueName: "MUIVerb"; ValueData: "비밀번호 설정"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\protect"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\protect"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\quick\shell\protect\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer protect --quick ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open"; ValueType: string; ValueName: "MUIVerb"; ValueData: "OfflinePDF에서 열기"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open"; ValueType: string; ValueName: "SubCommands"; ValueData: ""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "PDF 병합"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\merge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer merge ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\split"; ValueType: string; ValueName: "MUIVerb"; ValueData: "PDF 분할"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\split"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\split"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\split\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer split ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\compress"; ValueType: string; ValueName: "MUIVerb"; ValueData: "PDF 압축"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\compress"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\compress"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\compress\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer compress ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\upscale"; ValueType: string; ValueName: "MUIVerb"; ValueData: "AI 업스케일"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\upscale"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\upscale"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\upscale\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer upscale ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\unlock"; ValueType: string; ValueName: "MUIVerb"; ValueData: "비밀번호 해제"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\unlock"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\unlock"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\unlock\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer unlock ""%1"""; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\protect"; ValueType: string; ValueName: "MUIVerb"; ValueData: "비밀번호 설정"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\protect"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\protect"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OfflinePDF.exe"",0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF\shell\open\shell\protect\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OfflinePDF.exe"" --explorer protect ""%1"""; Tasks: explorermenu

[Files]
; The same files as the portable ZIP, including licenses and corresponding sources.
Source: "..\dist\OfflinePDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Drop files of an earlier version that this version no longer ships.
Type: filesandordirs; Name: "{app}\_internal"
; 1.0.0 carried the sources inside the program folder; they are now a separate download.
Type: filesandordirs; Name: "{app}\dependency-sources"
Type: files; Name: "{app}\CorrespondingSource.zip"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\OfflinePDF.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\OfflinePDF.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OfflinePDF.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
