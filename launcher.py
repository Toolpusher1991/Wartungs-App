import os
import sys
import webbrowser
from threading import Timer
from waitress import serve
from app import app

def open_browser():
    webbrowser.open('http://127.0.0.1:5000')

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if __name__ == '__main__':
    # Stelle sicher, dass wir im richtigen Verzeichnis sind
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    
    # Setze den Instance Path für Flask
    app.instance_path = os.path.join(os.getcwd(), 'instance')
    os.makedirs(app.instance_path, exist_ok=True)

    # Öffne den Browser nach 1.5 Sekunden
    Timer(1.5, open_browser).start()
    
    # Starte den Server
    print("Wartungs-App wird gestartet...")
    print("Bitte schließen Sie dieses Fenster nicht, solange Sie die App verwenden.")
    serve(app, host='127.0.0.1', port=5000)