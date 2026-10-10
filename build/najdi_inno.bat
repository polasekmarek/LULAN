@echo off
rem ===================================================================
rem  Najde prekladac Inno Setupu (ISCC.exe) a vrati cestu v INNO.
rem
rem  Vola se z jineho davkoveho souboru:
rem
rem      call "%~dp0najdi_inno.bat"
rem      if not defined INNO ( ...neni nainstalovan... )
rem
rem  Hleda ve ctyrech krocich, od nejspolehlivejsiho:
rem    0. promenna INNO_SETUP   - kdyz si ji uzivatel nastavi rucne
rem    1. PATH                  - kdyz si ISCC pridal mezi programy
rem    2. registr               - kam se Inno Setup opravdu nainstaloval
rem    3. obvykla umisteni      - zaloha, kdyz registr nic nerekne
rem
rem  Pozor na zavorky
rem  ----------------
rem  Hodnota %ProgramFiles(x86)% obsahuje zavorky. Kdyz takova promenna
rem  stoji uvnitr bloku for nebo if, uzavre ho predcasne a cmd zhavaruje
rem  hlaskou typu "ms was unexpected at this time". Proto se tu zadny
rem  blok se zavorkami nepouziva: vetvi se pres goto a kandidati se
rem  overuji podprogramem :overit.
rem ===================================================================
setlocal
set "NALEZENO="

rem --- 0. rucne zadana cesta ------------------------------------------
rem Ceka se bud adresar s Inno Setupem, nebo primo ISCC.exe.
if defined INNO_SETUP call :overit "%INNO_SETUP%"
if defined INNO_SETUP call :overit_exe "%INNO_SETUP%"
if defined NALEZENO goto :hotovo

rem --- 1. na PATH ------------------------------------------------------
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined NALEZENO set "NALEZENO=%%I"
if defined NALEZENO goto :hotovo

rem --- 2. registr ------------------------------------------------------
rem Inno Setup se zapisuje jako "Inno Setup N_is1". Prochazi se obe
rem vetve registru (pro vsechny uzivatele i jen pro prihlaseneho)
rem a obe zrcadla (64bit i 32bit), od novejsi rady ke starsi.
call :registr "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"
call :registr "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"
call :registr "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"
call :registr "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
call :registr "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
call :registr "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
if defined NALEZENO goto :hotovo

rem --- 3. obvykla umisteni ---------------------------------------------
rem Instalace jen pro prihlaseneho uzivatele konci v AppData\Local,
rem instalace pro vsechny v Program Files.
call :overit "%LOCALAPPDATA%\Programs\Inno Setup 7"
call :overit "%LOCALAPPDATA%\Programs\Inno Setup 6"
call :overit "%LOCALAPPDATA%\Programs\Inno Setup"
call :overit "%ProgramFiles%\Inno Setup 7"
call :overit "%ProgramFiles%\Inno Setup 6"
call :overit "%ProgramFiles%\Inno Setup"

rem Zavorky v nazvu se prirazuji mimo blok, jinak by rozbily parser.
set "PF86=%ProgramFiles(x86)%"
call :overit "%PF86%\Inno Setup 7"
call :overit "%PF86%\Inno Setup 6"
call :overit "%PF86%\Inno Setup"

rem Na 32bitovem cmd ukazuje %ProgramFiles% do (x86); tohle miri jinam.
if defined ProgramW6432 call :overit "%ProgramW6432%\Inno Setup 7"
if defined ProgramW6432 call :overit "%ProgramW6432%\Inno Setup 6"

:hotovo
endlocal & set "INNO=%NALEZENO%"
exit /b 0


rem --- podprogramy -----------------------------------------------------

rem Precte InstallLocation z jednoho klice registru.
:registr
if defined NALEZENO exit /b 0
for /f "tokens=2,*" %%A in ('reg query %1 /v InstallLocation 2^>nul ^| find "InstallLocation"') do call :overit "%%B"
exit /b 0

rem Overi adresar - hleda v nem ISCC.exe.
:overit
if defined NALEZENO exit /b 0
set "KAND=%~1"
if not defined KAND exit /b 0
if "%KAND:~-1%"=="\" set "KAND=%KAND:~0,-1%"
if exist "%KAND%\ISCC.exe" set "NALEZENO=%KAND%\ISCC.exe"
exit /b 0

rem Overi cestu zadanou primo na ISCC.exe.
:overit_exe
if defined NALEZENO exit /b 0
set "KAND=%~1"
if not defined KAND exit /b 0
if exist "%KAND%" if /i "%~nx1"=="ISCC.exe" set "NALEZENO=%KAND%"
exit /b 0
