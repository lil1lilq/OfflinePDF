#define AppName "오프라인 PDF 업무도구"
#define AppVersion "0.1.0"
[Setup]
AppId={{9DC9CDFB-9463-416E-B5AB-E5E49805C3A7}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\OfflinePDF
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=OfflinePDF-Setup-Windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\OfflinePDF.exe
CloseApplications=yes
[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
[Files]
Source: "..\dist\OfflinePDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\OfflinePDF.exe"
Name: "{group}\{#AppName}"; Filename: "{app}\OfflinePDF.exe"
Name: "{group}\사용 안내"; Filename: "{app}\USER_GUIDE_KO.txt"
[Run]
Filename: "{app}\OfflinePDF.exe"; Description: "{#AppName} 실행"; Flags: nowait postinstall skipifsilent
