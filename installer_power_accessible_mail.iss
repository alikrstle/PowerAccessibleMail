#define MyAppName "Power Accessible Mail"
#define MyAppVersion "1.2.13"
#define MyAppPublisher "Soljan.AlSharq."
#define MyAppExeName "Power Accessible Mail.exe"
#define MyAppIcon "assets\branding\power_accessible_mail.ico"
#define MyAppUninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{7F4F2C96-105C-49C0-AD57-752CE99BCDC7}_is1"

#ifndef TargetArchitecture
  #define TargetArchitecture "x64"
#endif

#ifdef SignedBuild
  #define OutputSuffix ""
#else
  #define OutputSuffix "-UNSIGNED"
#endif

[Setup]
AppId={{7F4F2C96-105C-49C0-AD57-752CE99BCDC7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments=Developed by Soljan.AlSharq.; owned by Ali Al-Amir
DefaultDirName={localappdata}\Programs\SoljanAlSharq\{#MyAppName}
DefaultGroupName=SoljanAlSharq\{#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no
DisableFinishedPage=no
ShowLanguageDialog=yes
OutputDir=release\installer
OutputBaseFilename=PowerAccessibleMailSetup-{#MyAppVersion}-win-{#TargetArchitecture}{#OutputSuffix}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
#if TargetArchitecture == "x64"
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesAllowed=x86compatible
#endif
VersionInfoVersion=1.2.13.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (c) 2026 Soljan.AlSharq.; owner Ali Al-Amir
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
#ifdef SignedBuild
SignTool=PowerAccessibleMail
SignedUninstaller=yes
SignToolRetryCount=3
#endif

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"; InfoBeforeFile: "installer_info_ar.txt"
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "installer_info_en.txt"

[CustomMessages]
arabic.ReadLocalizedReadme=قراءة دليل البرنامج العربي
english.ReadLocalizedReadme=Read the English README
arabic.LaunchLocalizedApp=تشغيل البرنامج بعد إنهاء التثبيت
english.LaunchLocalizedApp=Launch the application after Setup finishes
arabic.AcceptPrivacy=أنا أوافق على شروط الخصوصية
english.AcceptPrivacy=I agree to the privacy terms
arabic.UpdateTitle=تحديث Power Accessible Mail
english.UpdateTitle=Update Power Accessible Mail
arabic.UpdateDescription=تم العثور على إصدار أقدم مثبت على هذا الجهاز
english.UpdateDescription=An older installed version was found on this computer
arabic.UpdateBody=الإصدار المثبت هو %s، والإصدار الجديد هو %s. اضغط تحديث الآن للمتابعة أو إغلاق للخروج من المثبت.
english.UpdateBody=Installed version: %s. New version: %s. Select Update now to continue or Close to exit Setup.
arabic.UpdateNow=تحديث الآن
english.UpdateNow=Update now
arabic.CloseSetup=إغلاق
english.CloseSetup=Close

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
#ifdef SignedBuild
Source: "release\win-{#TargetArchitecture}\Power Accessible Mail\Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion signcheck
#else
Source: "release\win-{#TargetArchitecture}\Power Accessible Mail\Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif
Source: "release\win-{#TargetArchitecture}\Power Accessible Mail\*"; Excludes: "Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installer_readme_ar.txt"; DestDir: "{app}"; DestName: "README_AR.txt"; Flags: ignoreversion
Source: "installer_readme_en.txt"; DestDir: "{app}"; DestName: "README_EN.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\README_AR.txt"; Description: "{cm:ReadLocalizedReadme}"; Flags: shellexec nowait postinstall skipifsilent; Languages: arabic
Filename: "{app}\README_EN.txt"; Description: "{cm:ReadLocalizedReadme}"; Flags: shellexec nowait postinstall skipifsilent; Languages: english
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchLocalizedApp}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifdoesntexist; Check: IsInternalUpdate

[Code]
var
  PrivacyAgreementCheck: TNewCheckBox;
  UpdatePage: TWizardPage;
  UpdateMessage: TNewStaticText;
  InstalledVersion: String;
  UpdateMode: Boolean;

function IsInternalUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATEFROMAPP|0}') = '1';
end;

function ReadInstalledVersion(var Version: String): Boolean;
begin
  Result := RegQueryStringValue(
    HKCU, '{#MyAppUninstallKey}', 'DisplayVersion', Version);
  if not Result then
    Result := RegQueryStringValue(
      HKLM, '{#MyAppUninstallKey}', 'DisplayVersion', Version);
end;

function NextVersionPart(var Version: String): Integer;
var
  Separator: Integer;
  Part: String;
begin
  Separator := Pos('.', Version);
  if Separator > 0 then
  begin
    Part := Copy(Version, 1, Separator - 1);
    Delete(Version, 1, Separator);
  end
  else
  begin
    Part := Version;
    Version := '';
  end;
  Result := StrToIntDef(Part, 0);
end;

function IsVersionOlder(Installed, Current: String): Boolean;
var
  Index: Integer;
  InstalledPart: Integer;
  CurrentPart: Integer;
begin
  Result := False;
  for Index := 1 to 4 do
  begin
    InstalledPart := NextVersionPart(Installed);
    CurrentPart := NextVersionPart(Current);
    if InstalledPart < CurrentPart then
    begin
      Result := True;
      Exit;
    end;
    if InstalledPart > CurrentPart then
      Exit;
  end;
end;

procedure UpdatePrivacyNextButton;
begin
  if WizardForm.CurPageID = wpInfoBefore then
    WizardForm.NextButton.Enabled := PrivacyAgreementCheck.Checked
  else
    WizardForm.NextButton.Enabled := True;
end;

procedure PrivacyAgreementCheckClick(Sender: TObject);
begin
  UpdatePrivacyNextButton;
end;

procedure InitializeWizard;
begin
  UpdateMode := ReadInstalledVersion(InstalledVersion) and
    IsVersionOlder(InstalledVersion, '{#MyAppVersion}');
  if UpdateMode then
  begin
    UpdatePage := CreateCustomPage(
      wpWelcome, CustomMessage('UpdateTitle'),
      CustomMessage('UpdateDescription'));
    UpdateMessage := TNewStaticText.Create(UpdatePage.Surface);
    UpdateMessage.Parent := UpdatePage.Surface;
    UpdateMessage.Left := 0;
    UpdateMessage.Top := ScaleY(16);
    UpdateMessage.Width := UpdatePage.SurfaceWidth;
    UpdateMessage.AutoSize := False;
    UpdateMessage.WordWrap := True;
    UpdateMessage.Height := ScaleY(100);
    UpdateMessage.Caption := Format(
      CustomMessage('UpdateBody'), [InstalledVersion, '{#MyAppVersion}']);
  end;

  PrivacyAgreementCheck := TNewCheckBox.Create(WizardForm.InfoBeforePage);
  PrivacyAgreementCheck.Parent := WizardForm.InfoBeforePage;
  PrivacyAgreementCheck.Caption := CustomMessage('AcceptPrivacy');
  PrivacyAgreementCheck.Checked := False;
  PrivacyAgreementCheck.TabStop := True;
  PrivacyAgreementCheck.TabOrder := WizardForm.InfoBeforeMemo.TabOrder + 1;
  PrivacyAgreementCheck.Left := WizardForm.InfoBeforeMemo.Left;
  PrivacyAgreementCheck.Width := WizardForm.InfoBeforePage.ClientWidth;
  PrivacyAgreementCheck.OnClick := @PrivacyAgreementCheckClick;
  WizardForm.InfoBeforeMemo.Height :=
    WizardForm.InfoBeforeMemo.Height - ScaleY(30);
  PrivacyAgreementCheck.Top := WizardForm.InfoBeforeMemo.Top +
    WizardForm.InfoBeforeMemo.Height + ScaleY(8);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if UpdateMode then
  begin
    if CurPageID = UpdatePage.ID then
    begin
      WizardForm.NextButton.Caption := CustomMessage('UpdateNow');
      WizardForm.CancelButton.Caption := CustomMessage('CloseSetup');
      WizardForm.ActiveControl := WizardForm.NextButton;
    end;
  end;
  UpdatePrivacyNextButton;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := UpdateMode and
    ((PageID = wpWelcome) or
     (PageID = wpInfoBefore) or
     (PageID = wpSelectDir) or
     (PageID = wpSelectProgramGroup) or
     (PageID = wpSelectTasks) or
     (PageID = wpReady));
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if UpdateMode then
  begin
    if CurPageID = UpdatePage.ID then
      Confirm := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := (CurPageID <> wpInfoBefore) or PrivacyAgreementCheck.Checked;
end;
