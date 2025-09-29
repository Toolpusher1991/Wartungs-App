#!/usr/bin/env python3
"""
Update-Skript für die Wartungs-App Datenbank
Fügt die neuen Spalten für Material-Bestellung hinzu
"""

import sqlite3
import os
from datetime import datetime

def update_database():
    """Fügt die neuen Spalten für Material-Bestellung zur Problem-Tabelle hinzu"""
    
    db_path = 'instance/problems.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Datenbank-Datei {db_path} nicht gefunden!")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Prüfe existierende Spalten
        cursor.execute("PRAGMA table_info(problem)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Existierende Spalten: {', '.join(columns)}")
        
        new_columns = [
            ('mm_nummer', 'VARCHAR(100)'),
            ('teil_beschreibung', 'VARCHAR(200)'),
            ('besteller_id', 'INTEGER')
        ]
        
        # Füge neue Spalten hinzu, falls sie noch nicht existieren
        for column_name, column_type in new_columns:
            if column_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE problem ADD COLUMN {column_name} {column_type}")
                    print(f"✅ Spalte '{column_name}' hinzugefügt")
                except sqlite3.OperationalError as e:
                    print(f"⚠️ Fehler beim Hinzufügen der Spalte '{column_name}': {e}")
            else:
                print(f"ℹ️ Spalte '{column_name}' existiert bereits")
        
        # Foreign Key Constraint für besteller_id wird zur Laufzeit von SQLAlchemy verwaltet
        
        conn.commit()
        print("✅ Datenbank erfolgreich aktualisiert!")
        
        # Prüfe finale Spalten
        cursor.execute("PRAGMA table_info(problem)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Finale Spalten: {', '.join(columns)}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Datenbankfehler: {e}")
        return False

if __name__ == '__main__':
    print("🔧 Wartungs-App Datenbank Update")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    if update_database():
        print("\n🎉 Update erfolgreich abgeschlossen!")
    else:
        print("\n❌ Update fehlgeschlagen!")