#define MyAppName "Power Accessible Mail"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Soljan Al Sharq"
#define MyAppExeName "Power Accessible Mail.exe"

#ifdef SignedBuild
  #define OutputSuffix ""
#else
  #define OutputSuffix "-UNSIGNED"
#endif

[Setup]
AppId={{E87E82D0-9E81-4F20-8E23-3A6D7E2F9B01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=release\installer
OutputBaseFilename=PowerAccessibleMailSetup-{#MyAppVersion}-win-x64{#OutputSuffix}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion=1.2.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
#ifdef SignedBuild
SignTool=PowerAccessibleMail
SignedUninstaller=yes
SignToolRetryCount=3
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
#ifdef SignedBuild
Source: "release\win-x64\Power Accessible Mail\Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion signcheck
#else
Source: "release\win-x64\Power Accessible Mail\Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif
Source: "release\win-x64\Power Accessible Mail\*"; Excludes: "Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
