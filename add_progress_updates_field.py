#!/usr/bin/env python3
"""
Migrations-Script: Fügt das progress_updates Feld zur Problem-Tabelle hinzu
"""

from app import app, db
from sqlalchemy import text

def add_progress_updates_field():
    """Fügt das progress_updates Feld zur Problem-Tabelle hinzu"""
    with app.app_context():
        try:
            # Prüfen ob das Feld bereits existiert
            result = db.session.execute(text("PRAGMA table_info(problem)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'progress_updates' not in columns:
                print("Füge progress_updates Feld zur Problem-Tabelle hinzu...")
                db.session.execute(text("ALTER TABLE problem ADD COLUMN progress_updates TEXT"))
                db.session.commit()
                print("✅ progress_updates Feld erfolgreich hinzugefügt!")
            else:
                print("✅ progress_updates Feld existiert bereits.")
                
        except Exception as e:
            print(f"❌ Fehler beim Hinzufügen des Feldes: {e}")
            db.session.rollback()

if __name__ == '__main__':
    add_progress_updates_field()