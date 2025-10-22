@echo off
setlocal

:: Usage:
::   scripts\run_csv.cmd [IN] [OUT] [BUILD_ID] [PLOT_KPI] [SLOPE_7D] [PROMOTE] [DEMOTE] [PLOTS_DIR]
::
:: Defaults (safe for pilots)
set "IN=%~1"
set "OUT=%~2"
set "BUILD_ID=%~3"
set "PLOT_KPI=%~4"
set "SLOPE_7D=%~5"
set "PROMOTE=%~6"
set "DEMOTE=%~7"
set "PLOTS_DIR=%~8"

if "%IN%"==""        set "IN=templates\mini_calc_mapper_template.csv"
if "%OUT%"==""       set "OUT=mini_calc_output.csv"
if "%BUILD_ID%"==""  set "BUILD_ID=csvPilot"
if "%PLOT_KPI%"==""  set "PLOT_KPI=Revenue_actual"
if "%SLOPE_7D%"==""  set "SLOPE_7D=-0.02"
if "%PROMOTE%"==""   set "PROMOTE=0.05"
if "%DEMOTE%"==""    set "DEMOTE=-0.05"
if "%PLOTS_DIR%"=="" set "PLOTS_DIR=Plots"

:: Preflight checks
if not exist "%IN%" (
  echo [ERR] Input CSV not found: "%IN%"
  exit /b 2
)

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERR] Python 3.8+ not found on PATH.
  exit /b 3
)

if not exist "%PLOTS_DIR%" mkdir "%PLOTS_DIR%" >nul 2>&1

echo === SSM-Audit Mini Calculator (CSV mode) ===
echo IN=%IN%
echo OUT=%OUT%
echo BUILD_ID=%BUILD_ID%
echo PLOT_KPI=%PLOT_KPI%
echo PLOTS_DIR=%PLOTS_DIR%
echo promote=%PROMOTE% demote=%DEMOTE% slope_7d=%SLOPE_7D%
echo ----------------------------------------------

:: Run with mapper auto-detect, hysteresis, alerts, CSV-tagged plot, and native SDI (+ SDI plot)
python ssm_audit_mini_calc.py "%IN%" "%OUT%" ^
  --compute_a auto ^
  --build_id "%BUILD_ID%" ^
  --promote %PROMOTE% --demote %DEMOTE% --gamma 1.0 --eps_a 1e-6 --eps_w 1e-12 ^
  --alerts_csv alerts.csv --slope_7d %SLOPE_7D% ^
  --plot_kpi "%PLOT_KPI%" --plots_dir "%PLOTS_DIR%" --plot_tag CSV ^
  --color_a orange ^
  --sdi --sdi_plot

set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo [ERR] mini_calc exited with code %ERR%
  exit /b %ERR%
)

echo.
echo [OK] Finished.
echo   CSV   : "%OUT%"
echo   Alerts: "alerts.csv" (if any)
echo   Plot  : "%PLOTS_DIR%\%PLOT_KPI%_CSV.png" (if KPI present)
echo   SDI   : "%PLOTS_DIR%\SDI.png"
echo ----------------------------------------------
endlocal
