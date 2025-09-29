#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Datenbank-Migration für po_nummer und lieferdatum Felder
"""

import sys
import os

# App-Pfad hinzufügen
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def migrate_material_item_table():
    """Fügt po_nummer und lieferdatum Spalten zur material_item Tabelle hinzu"""
    
    with app.app_context():
        print("🔧 Führe Datenbank-Migration durch...")
        
        try:
            from sqlalchemy import text
            
            # Prüfe, ob die Spalten bereits existieren
            with db.engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info(material_item)"))
                columns = [row[1] for row in result]
                print(f"📋 Vorhandene Spalten: {columns}")
                
                # Füge po_nummer Spalte hinzu, falls sie nicht existiert
                if 'po_nummer' not in columns:
                    print("➕ Füge po_nummer Spalte hinzu...")
                    conn.execute(text("ALTER TABLE material_item ADD COLUMN po_nummer VARCHAR(50)"))
                    conn.commit()
                    print("✅ po_nummer Spalte hinzugefügt")
                else:
                    print("ⓘ po_nummer Spalte existiert bereits")
                
                # Füge lieferdatum Spalte hinzu, falls sie nicht existiert
                if 'lieferdatum' not in columns:
                    print("➕ Füge lieferdatum Spalte hinzu...")
                    conn.execute(text("ALTER TABLE material_item ADD COLUMN lieferdatum DATE"))
                    conn.commit()
                    print("✅ lieferdatum Spalte hinzugefügt")
                else:
                    print("ⓘ lieferdatum Spalte existiert bereits")
                
                # Prüfe final result
                result = conn.execute(text("PRAGMA table_info(material_item)"))
                columns = [row[1] for row in result]
                print(f"📋 Spalten nach Migration: {columns}")
            
            print("🎉 Datenbank-Migration erfolgreich abgeschlossen!")
            
        except Exception as e:
            print(f"❌ Fehler bei der Migration: {e}")
            return False
        
        return True

if __name__ == '__main__':
    migrate_material_item_table()