@echo off
rem ===================================================================
rem  Sestaveni LULANu pro Windows.
rem
rem  Spoustet z korene projektu:   build\sestavit.bat
rem
rem  Vysledek:
rem    dist\LULAN\LULAN.exe        program se vsim, co potrebuje
rem    build\vystup\LULAN-setup-*.exe   instalator (kdyz je Inno Setup)
rem
rem  Predpoklady:
rem    - Python 3.11 nebo novejsi
rem    - virtualni prostredi .venv s balicky z requirements.txt
rem    - PyInstaller  (pip install pyinstaller)
rem    - Inno Setup 6 nebo 7 (volitelne, pro krok 4)
rem ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo.
echo === 1. Kontrola souboru, ktere aplikace potrebuje ===

set CHYBI=0
call :overit "dtb\LULAN_dtb_001.db"
call :overit "dtb\ricni_sit.db"
call :overit "dtb\ciselnik_traits.csv"
call :overit "dtb\hodnoceni_zkratky.csv"
call :overit "img\LULAN_icon.ico"
call :overit "img\filtr_ikona.png"
call :overit "img\filtr_ikona@2x.png"
call :overit "src\GIS\hrcr_S42.shp"
call :overit "src\GIS\hlavni_toky_S42.shp"
call :overit "LICENSE"
call :overit "VERZE"

if not "%CHYBI%"=="0" (
    echo.
    echo Chybi %CHYBI% souboru. Bez nich se cast programu nespusti spravne.
    echo Podrobnosti jsou v UKLID.md, kapitola 1.
    echo.
    choice /c AN /m "Pokracovat presto"
    if errorlevel 2 exit /b 1
)

echo.
echo === 2. Virtualni prostredi ===
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo Aktivovano .venv
) else (
    echo .venv nenalezeno, pouziva se systemovy Python.
)

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller neni nainstalovan. Instaluji...
    python -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)

echo.
echo === 3. Sestaveni programu ===
rem Predchozi vysledek se maze, aby v nem nezustaly stare soubory.
if exist "dist\LULAN" rmdir /s /q "dist\LULAN"
if exist "build\LULAN" rmdir /s /q "build\LULAN"

pyinstaller build\lulan.spec --noconfirm --distpath dist --workpath build\prace
if errorlevel 1 (
    echo.
    echo Sestaveni selhalo.
    exit /b 1
)

if not exist "dist\LULAN\LULAN.exe" (
    echo.
    echo LULAN.exe nevznikl - neco je spatne.
    exit /b 1
)
echo Hotovo: dist\LULAN\LULAN.exe

echo.
echo === 4. Instalator ===
call "%~dp0najdi_inno.bat"
rem Pozor: %INNO% muze obsahovat zavorky (Program Files (x86)), takze se
rem netestuje pres if "%INNO%"=="" - to by parser cmd rozbilo.
if not defined INNO goto :bez_instalatoru

echo Prekladac: %INNO%

"%INNO%" build\lulan.iss
if errorlevel 1 goto :instalator_selhal
echo Hotovo: build\vystup\
goto :konec

:bez_instalatoru
echo Inno Setup nenalezen - instalator se nevyrobi.
echo Program presto funguje: spustte dist\LULAN\LULAN.exe
echo.
echo Az ho nainstalujete, staci spustit build\instalator.bat -
echo program uz sestaveny je a znovu se prekladat nemusi.
echo Ke stazeni: https://jrsoftware.org/isdl.php
goto :konec

:instalator_selhal
echo Vyroba instalatoru selhala.
exit /b 1

:konec
echo.
echo === Sestaveni dokonceno ===
echo.
echo Program neni podepsany, takze pri prvnim spusteni ukaze Windows
echo varovani SmartScreen. Jak s tim nalozit, popisuje PODPIS.md.
exit /b 0

:overit
if exist "%~1" (
    echo   OK    %~1
) else (
    echo   CHYBI %~1
    set /a CHYBI+=1
)
exit /b 0
