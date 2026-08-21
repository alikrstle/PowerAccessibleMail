#define MyAppName "Power Accessible Mail"
#define MyAppVersion "1.3.0"
#define MyAppPublisher "Soljan.AlSharq."
#define MyAppExeName "Power Accessible Mail.exe"
#define MyAppIcon "assets\branding\power_accessible_mail.ico"
#define MyAppURL "https://soljan-alsharq.com/"
#define MyAppSupportURL "https://soljan-alsharq.com/support.html"
#define MyAppUpdatesURL "https://soljan-alsharq.com/downloads.html"
#define MyAppContact "support@soljan-alsharq.com"
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
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppSupportURL}
AppUpdatesURL={#MyAppUpdatesURL}
AppContact={#MyAppContact}
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
#ifdef SignedBuild
Compression=lzma
SolidCompression=yes
#else
Compression=zip
SolidCompression=no
#endif
WizardStyle=modern
PrivilegesRequired=lowest
ChangesAssociations=yes
#if TargetArchitecture == "x64"
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesAllowed=x86compatible
#endif
VersionInfoVersion=1.3.0.0
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
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "installer_info_en.txt"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"; InfoBeforeFile: "installer_info_ar.txt"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"; InfoBeforeFile: "installer_info_fr.txt"

[CustomMessages]
arabic.ReadLocalizedReadme=قراءة دليل البرنامج العربي
english.ReadLocalizedReadme=Read the English README
french.ReadLocalizedReadme=Lire le guide du programme en français
arabic.LaunchLocalizedApp=تشغيل البرنامج بعد إنهاء التثبيت
english.LaunchLocalizedApp=Launch the application after Setup finishes
french.LaunchLocalizedApp=Lancer l'application à la fin de l'installation
arabic.DefaultMailIntegration=تكامل البريد الافتراضي في Windows
english.DefaultMailIntegration=Windows default email integration
french.DefaultMailIntegration=Intégration de la messagerie par défaut de Windows
arabic.OpenDefaultMailSettings=فتح إعدادات Windows لاختيار Power Accessible Mail كتطبيق البريد الافتراضي
english.OpenDefaultMailSettings=Open Windows Settings to choose Power Accessible Mail as the default email app
french.OpenDefaultMailSettings=Ouvrir les paramètres Windows pour choisir Power Accessible Mail comme application de messagerie par défaut
arabic.AcceptPrivacy=أنا أوافق على شروط الخصوصية
english.AcceptPrivacy=I agree to the privacy terms
french.AcceptPrivacy=J'accepte les conditions de confidentialité
arabic.UpdateTitle=تحديث Power Accessible Mail
english.UpdateTitle=Update Power Accessible Mail
french.UpdateTitle=Mise à jour de Power Accessible Mail
arabic.UpdateDescription=تم العثور على إصدار أقدم مثبت على هذا الجهاز
english.UpdateDescription=An older installed version was found on this computer
french.UpdateDescription=Une ancienne version est installée sur cet ordinateur
arabic.UpdateBody=الإصدار المثبت هو %s، والإصدار الجديد هو %s. اضغط تحديث الآن للمتابعة أو إغلاق للخروج من المثبت.
english.UpdateBody=Installed version: %s. New version: %s. Select Update now to continue or Close to exit Setup.
french.UpdateBody=Version installée : %s. Nouvelle version : %s. Sélectionnez Mettre à jour maintenant pour continuer ou Fermer pour quitter l'installation.
arabic.UpdateNow=تحديث الآن
english.UpdateNow=Update now
french.UpdateNow=Mettre à jour maintenant
arabic.CloseSetup=إغلاق
english.CloseSetup=Close
french.CloseSetup=Fermer

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "defaultmailsettings"; Description: "{cm:OpenDefaultMailSettings}"; GroupDescription: "{cm:DefaultMailIntegration}"; Flags: unchecked

[Files]
#ifdef SignedBuild
Source: "release\win-{#TargetArchitecture}\Power Accessible Mail\Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion signcheck
#else
Source: "release\win-{#TargetArchitecture}\Power Accessible Mail\Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif
Source: "release\win-{#TargetArchitecture}\Power Accessible Mail\*"; Excludes: "Power Accessible Mail.exe"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installer_readme_ar.txt"; DestDir: "{app}"; DestName: "README_AR.txt"; Flags: ignoreversion
Source: "installer_readme_en.txt"; DestDir: "{app}"; DestName: "README_EN.txt"; Flags: ignoreversion
Source: "installer_readme_fr.txt"; DestDir: "{app}"; DestName: "README_FR.txt"; Flags: ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail"; ValueType: string; ValueName: ""; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Accessible email client with NVDA support"
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\Capabilities"; ValueType: dword; ValueName: "Hidden"; ValueData: "0"
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\Capabilities\Startmenu"; ValueType: string; ValueName: "Mail"; ValueData: "PowerAccessibleMail"
Root: HKCU; Subkey: "Software\Clients\Mail\PowerAccessibleMail\Capabilities\UrlAssociations"; ValueType: string; ValueName: "mailto"; ValueData: "PowerAccessibleMail.mailto"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\Clients\Mail\PowerAccessibleMail\Capabilities"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto"; ValueType: string; ValueName: ""; ValueData: "Power Accessible Mail email link"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Power Accessible Mail email link"
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto\Application"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto\Application"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Accessible email client with NVDA support"
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto\Application"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto\Application"; ValueType: string; ValueName: "ApplicationCompany"; ValueData: "{#MyAppPublisher}"
Root: HKCU; Subkey: "Software\Classes\PowerAccessibleMail.mailto\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\mailto\OpenWithProgids"; ValueType: none; ValueName: "PowerAccessibleMail.mailto"; Flags: uninsdeletevalue

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\README_AR.txt"; Description: "{cm:ReadLocalizedReadme}"; Flags: shellexec nowait postinstall skipifsilent; Languages: arabic
Filename: "{app}\README_EN.txt"; Description: "{cm:ReadLocalizedReadme}"; Flags: shellexec nowait postinstall skipifsilent; Languages: english
Filename: "{app}\README_FR.txt"; Description: "{cm:ReadLocalizedReadme}"; Flags: shellexec nowait postinstall skipifsilent; Languages: french
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchLocalizedApp}"; Flags: nowait postinstall skipifsilent
Filename: "ms-settings:defaultapps?registeredAppUser=Power%20Accessible%20Mail"; Description: "{cm:OpenDefaultMailSettings}"; Flags: shellexec nowait postinstall skipifsilent; Tasks: defaultmailsettings; Check: not IsInternalUpdate
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
