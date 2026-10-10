; ===================================================================
;  Instalator LULANu pro Windows (Inno Setup 6 nebo 7)
;
;  Preklad:  ISCC.exe build\lulan.iss
;  Vstupem je dist\LULAN\, ktery vyrobi build\sestavit.bat.
;
;  Skript prekladaji obe rady. Inno Setup 7 je zpetne kompatibilni se
;  sestkou, takze nic prepisovat netreba; sedmicka navic umi sestavit
;  64bitovy instalator, coz se nize zapina podminene.
;
;  Kam se co instaluje
;  -------------------
;  Program i predloha databaze   Program Files\LULAN   jen ke cteni
;  Data uzivatele                AppData\Local\LULAN   sem si program
;                                predlohu zkopiruje pri prvnim spusteni
;
;  Do Program Files bezny uzivatel zapisovat nesmi, takze databaze tam
;  zustat nemuze. Program si ji proto pri prvnim spusteni prenese do
;  svych dat - a odinstalace se jich nedotkne, takze o vlozene vzorky
;  nikdo neprijde.
; ===================================================================

#define Nazev "LULAN"

; Cislo verze se cte ze souboru VERZE v korenu projektu, aby se nemuselo
; udrzovat zvlast tady, v predpisu PyInstalleru a v obou skriptech pro
; macOS a Linux. Driv to tak bylo a verze se rozesly.
#define VerzeSoubor FileOpen("..\VERZE")
#define Verze Trim(FileRead(VerzeSoubor))
#expr FileClose(VerzeSoubor)
#if Verze == ""
  #error Soubor VERZE je prazdny nebo chybi.
#endif
#define Vydavatel "Masarykova univerzita & Výzkumný ústav vodohospodářský TGM, v.v.i."
#define Web "https://www.muni.cz, https://www.vuv.cz"
#define Spustitelny "LULAN.exe"

[Setup]
AppId={{8C4F1E2A-6B7D-4A31-9E55-2D3F7A1C9B04}
AppName={#Nazev}
AppVersion={#Verze}
AppVerName={#Nazev} {#Verze}
AppPublisher={#Vydavatel}
AppPublisherURL={#Web}
DefaultDirName={autopf}\{#Nazev}
DefaultGroupName={#Nazev}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=vystup
OutputBaseFilename=LULAN-setup-{#Verze}
SetupIconFile=..\img\LULAN_icon.ico
UninstallDisplayIcon={app}\{#Spustitelny}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Program je 64bitovy - na 32bitovem systemu instalaci rovnou odmitnout.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Inno Setup 7 umi vyrobit i 64bitovy instalator. Ma to dva prinosy:
; vetsi slovnik komprese (3,8 GB misto 1 GB), coz se u 88 MB dat hodi,
; a high-entropy ASLR, kterou nektere bezpecnostni politiky vyzaduji.
; Sestka direktivu nezna, proto je za podminkou - skript tak zustava
; prelozitelny obema radami.
#if Ver >= EncodeVer(7, 0, 0)
SetupArchitecture=x64
#endif
; Instalace pro vsechny uzivatele vyzaduje pravo spravce; kdyz ho
; uzivatel nema, Inno Setup nabidne instalaci jen pro nej.
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "plocha"; Description: "Vytvořit zástupce na ploše"; \
    GroupDescription: "Zástupci:"

[Files]
; Vsechno, co vyrobil PyInstaller, vcetne adresare dtb s predlohou
; databaze a s ricni siti.
Source: "..\dist\LULAN\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Nazev}"; Filename: "{app}\{#Spustitelny}"
Name: "{group}\Odinstalovat {#Nazev}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nazev}"; Filename: "{app}\{#Spustitelny}"; \
    Tasks: plocha

[Run]
Filename: "{app}\{#Spustitelny}"; \
    Description: "Spustit {#Nazev}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Prazdna slozka programu po odinstalaci; data uzivatele zustavaji.
Type: dirifempty; Name: "{app}"

[Code]
{ Zalomeni radku se sklada z Chr(13) a Chr(10) zamerne.
  V Pascalu se obvykle pise mrizka a cislo znaku, jenze preprocesor
  Inno Setupu bere mrizku na zacatku radku jako svoji direktivu - a
  zadna takova direktiva neexistuje, takze preklad skonci hlaskou
  "Unknown preprocessor directive". Plati to i uvnitr tohoto komentare:
  preprocesor bezi driv, nez se zdrojak vubec zacne cist jako Pascal.
  Zapis pres Chr() zadnou mrizku neobsahuje, takze je jedno, kam se
  radky zalomi. }

procedure CurStepChanged(CurStep: TSetupStep);
var
  Zprava: String;
  Kam: String;
begin
  if CurStep = ssPostInstall then
  begin
    Kam := ExpandConstant('{localappdata}\{#Nazev}');
    Zprava := 'Při prvním spuštění si program zkopíruje databázi do:'
      + Chr(13) + Chr(10) + Kam
      + Chr(13) + Chr(10) + Chr(13) + Chr(10)
      + 'Odinstalace programu tuto kopii nesmaže, takže o vložené '
      + 'vzorky nepřijdete.';
    MsgBox(Zprava, mbInformation, MB_OK);
  end;
end;
