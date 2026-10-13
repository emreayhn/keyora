; Keyora Inno Setup script
; Build:   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\keyora.iss
; Output:  installer\Output\Keyora-Setup-1.2.1.exe
;
; Önkoşul: önce `pyinstaller keyora.spec --clean --noconfirm` ile dist\Keyora.exe üret.

#define MyAppName       "Keyora"
#define MyAppVersion    "1.2.1"
#define MyAppPublisher  "Emre Ayhan"
#define MyAppExeName    "Keyora.exe"

[Setup]
; Aynı uygulama için sabit GUID — gelecek sürümlerde değiştirme.
AppId={{B9F4A8E2-1F4C-4E0E-9D5E-7A1A8E4A2B3C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=© 2026 Emre Ayhan — MIT License
VersionInfoVersion={#MyAppVersion}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir=Output
OutputBaseFilename=Keyora-Setup-{#MyAppVersion}
SetupIconFile=..\resources\keyora.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Uygulamalar listesinde "Keyora 1.2.1 sürümü" yerine yalnızca "Keyora"
UninstallDisplayName={#MyAppName}

Compression=lzma2
SolidCompression=yes

WizardStyle=modern
LicenseFile=..\LICENSE

; Güncelleme sırasında Keyora açıksa exe kilitli olur: Restart Manager ile
; kullanıcıya kapatmayı teklif et, kurulumdan sonra kendiliğinden yeniden açma.
CloseApplications=yes
RestartApplications=no

; Windows 10 (1809) ve üzeri
MinVersion=10.0.17763

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller onefile çıktısı — tüm bağımlılıklar zaten exe içinde.
Source: "..\dist\Keyora.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE";         DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";       DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[Code]
// Kaldırma kasayı silmez; kullanıcı nerede durduğunu bilsin.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    MsgBox('Keyora kaldırıldı. Kasanız ve yedekleriniz SİLİNMEDİ (Keyora''yı ' +
      'kullanan Windows hesabının klasöründe, varsayılan olarak):' + #13#10 +
      ExpandConstant('{localappdata}\Keyora') + #13#10#13#10 +
      'Ayarlar''dan başka bir yedek klasörü seçtiyseniz yedekler orada durur.' + #13#10#13#10 +
      'Keyora''yı yeniden kurarsanız aynı kasa açılır. Tamamen silmek ' +
      'istiyorsanız bu klasörü elle silin; master password olmadan kasa açılamaz.',
      mbInformation, MB_OK);
end;
