@echo off
echo Baue Wartungs-App...
pyinstaller --clean wartungs-app.spec
echo.
echo Build abgeschlossen!
echo Die fertige App befindet sich im Ordner "dist\Wartungs-App"
pause