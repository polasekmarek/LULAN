@echo off
rem ===================================================================
rem  Vyrobi jen instalator z uz sestaveneho programu.
rem
rem  Spoustet z korene projektu:   build\instalator.bat
rem
rem  Hodi se, kdyz program uz v dist\LULAN\ je a znovu sestavovat
rem  ho netreba - typicky kdyz se pri prvnim behu nenasel Inno Setup.
rem
rem  Kdyz Inno Setup sedi nekde neobvykle, jde cestu predat rovnou:
rem    build\instalator.bat "C:\cesta\k\Inno Setup 7"
rem ===================================================================
setlocal
cd /d "%~dp0.."

if not exist "dist\LULAN\LULAN.exe" goto :nesestaveno

if not "%~1"=="" set "INNO_SETUP=%~1"
call "%~dp0najdi_inno.bat"
if not defined INNO goto :nenalezen

echo Prekladac: %INNO%
echo.
"%INNO%" build\lulan.iss
if errorlevel 1 goto :selhalo

echo.
echo === Hotovo ===
dir /b "build\vystup\*.exe" 2>nul
exit /b 0


:nesestaveno
echo Program jeste neni sestaveny - chybi dist\LULAN\LULAN.exe
echo Spustte nejdriv:  build\sestavit.bat
exit /b 1

:nenalezen
echo.
echo Prekladac Inno Setupu (ISCC.exe) se nenasel.
echo.
echo Hledal jsem:
echo   - v promenne INNO_SETUP
echo   - na PATH
echo   - v registru pod "Inno Setup 7_is1" a "Inno Setup 6_is1"
echo   - v Program Files, Program Files ^(x86^) a AppData\Local\Programs
echo.
echo Kdyz uz Inno Setup nainstalovany mate, predejte cestu k nemu:
echo   build\instalator.bat "%%LOCALAPPDATA%%\Programs\Inno Setup 7"
echo.
echo Nebo spustte prekladac rucne:
echo   "cesta\k\ISCC.exe" build\lulan.iss
echo.
echo Ke stazeni: https://jrsoftware.org/isdl.php
exit /b 1

:selhalo
echo.
echo Vyroba instalatoru selhala.
exit /b 1
