import sqlite3
import os

def update_database():
    # Datenbank öffnen
    db_path = os.path.join('instance', 'problems.db')
    if not os.path.exists(db_path):
        print("Datenbank nicht gefunden, wird beim nächsten App-Start erstellt.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Prüfen ob 'images' Spalte bereits existiert
        cursor.execute("PRAGMA table_info(problem)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'images' not in columns:
            # Neue Spalte hinzufügen
            cursor.execute("ALTER TABLE problem ADD COLUMN images TEXT")
            conn.commit()
            print("✅ 'images' Spalte erfolgreich zur Problem-Tabelle hinzugefügt!")
        else:
            print("✅ 'images' Spalte existiert bereits.")
            
        # Prüfen ob 'assigned_to' Spalte bereits existiert
        if 'assigned_to' not in columns:
            # Neue Spalte für Benutzerzuweisung hinzufügen
            cursor.execute("ALTER TABLE problem ADD COLUMN assigned_to INTEGER")
            conn.commit()
            print("✅ 'assigned_to' Spalte erfolgreich zur Problem-Tabelle hinzugefügt!")
        else:
            print("✅ 'assigned_to' Spalte existiert bereits.")
            
    except Exception as e:
        print(f"❌ Fehler beim Aktualisieren der Datenbank: {e}")
    finally:
        conn.close()

    print("🚀 Datenbank-Update abgeschlossen!")

if __name__ == '__main__':
    update_database()