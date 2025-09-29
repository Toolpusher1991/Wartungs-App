@echo off
echo ========================================
echo Wartungs-App - SICHERE PRODUKTIONSVERSION
echo ========================================
echo.
echo WICHTIG: Diese Version läuft mit erhöhter Sicherheit:
echo - Debug-Modus DEAKTIVIERT
echo - CSRF-Schutz AKTIVIERT  
echo - Starker Secret Key verwendet
echo.
echo Die App ist erreichbar unter:
echo   http://192.168.188.20:5000
echo.
echo SICHERHEITSHINWEISE:
echo - Nur für Heimnetzwerk geeignet
echo - Für Internet: HTTPS erforderlich
echo - Ändern Sie Standard-Passwörter!
echo.
echo ========================================
echo.

REM Sichere Produktionsumgebung laden
set FLASK_ENV=production
set DEBUG=False

REM App mit virtuellem Environment starten
C:/Users/Nils/AppData/Roaming/Code/User/Wartungsordner/venv/Scripts/python.exe app.py
pause