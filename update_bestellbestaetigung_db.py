#!/usr/bin/env python3
"""
Update-Skript für die Wartungs-App Datenbank
Fügt die neuen Spalten für Bestellbestätigung hinzu
"""

import sqlite3
import os
from datetime import datetime

def update_database():
    """Fügt die neuen Spalten für Bestellbestätigung zur Problem-Tabelle hinzu"""
    
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
            ('bestellung_bestaetigt', 'BOOLEAN DEFAULT 0'),
            ('pr_nummer', 'VARCHAR(50)'),
            ('lieferdatum', 'DATE'),
            ('bestellung_bestaetigt_am', 'DATETIME')
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
    print("🔧 Wartungs-App Datenbank Update für Bestellbestätigung")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    if update_database():
        print("\n🎉 Update erfolgreich abgeschlossen!")
    else:
        print("\n❌ Update fehlgeschlagen!")