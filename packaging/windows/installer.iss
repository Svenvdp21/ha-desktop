; Inno Setup-installer voor Windows. Bouwen: iscc /DAppVersion=<versie> packaging\windows\installer.iss
; Installeert per gebruiker (geen beheerdersrechten nodig).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F2B3C1E-8D4A-4E7B-9A55-2C1D0E9F7A41}
AppName=Home Assistant Desktop (unofficial)
AppVersion={#AppVersion}
AppPublisher=Svenvdp21
AppPublisherURL=https://github.com/Svenvdp21/ha-desktop
DefaultDirName={localappdata}\Programs\Home Assistant Desktop
DefaultGroupName=Home Assistant Desktop
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=HomeAssistantDesktop-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\build\icon.ico
UninstallDisplayIcon={app}\ha-desktop.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\ha-desktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Home Assistant Desktop"; Filename: "{app}\ha-desktop.exe"
Name: "{autodesktop}\Home Assistant Desktop"; Filename: "{app}\ha-desktop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ha-desktop.exe"; Description: "{cm:LaunchProgram,Home Assistant Desktop}"; Flags: nowait postinstall skipifsilent

[Registry]
; Autostart-waarde die de app zelf kan aanmaken, opruimen bij verwijderen.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "com.nordicnode.HADesktop"; Flags: uninsdeletevalue dontcreatekey
