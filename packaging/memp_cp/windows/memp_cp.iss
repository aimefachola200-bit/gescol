; Installateur Windows de l'Application CP (MEMP).  iscc /DVersion=1.5.8 /DNom="MEMP CP" /DFichier=MEMP-CP /DId=bj.memp.cp memp_cp.iss
#ifndef Version
  #define Version "1.0"
#endif
#ifndef Nom
  #define Nom "MEMP CP"
#endif
#ifndef Fichier
  #define Fichier "MEMP-CP"
#endif
#ifndef Id
  #define Id "bj.memp.cp"
#endif

[Setup]
AppId={#Id}
AppName={#Nom}
AppVersion={#Version}
AppPublisher=Maître Aimé FACHOLA — MEMP Bénin
DefaultDirName={localappdata}\Programs\{#Nom}
DefaultGroupName={#Nom}
PrivilegesRequired=lowest
OutputDir=..\..\..\dist
OutputBaseFilename={#Fichier}-Installation-{#Version}
SetupIconFile=memp_cp.ico
UninstallDisplayIcon={app}\MEMP-CP.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "dist\MEMP-CP\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#Nom}"; Filename: "{app}\MEMP-CP.exe"
Name: "{userdesktop}\{#Nom}"; Filename: "{app}\MEMP-CP.exe"; Tasks: bureau

[Run]
Filename: "{app}\MEMP-CP.exe"; Description: "Lancer {#Nom}"; Flags: nowait postinstall skipifsilent
