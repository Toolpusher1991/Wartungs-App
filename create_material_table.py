#!/usr/bin/env python3
"""
Datenbank-Migration: MaterialItem-Tabelle erstellen
"""

import sqlite3
import os
from datetime import datetime

DATABASE_PATH = 'instance/problems.db'

def create_material_table():
    """Erstellt die MaterialItem-Tabelle"""
    if not os.path.exists('instance'):
        os.makedirs('instance')
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Prüfen ob Tabelle bereits existiert
    cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='material_item'
    ''')
    
    if cursor.fetchone():
        print("MaterialItem-Tabelle existiert bereits.")
        conn.close()
        return
    
    # MaterialItem-Tabelle erstellen
    cursor.execute('''
        CREATE TABLE material_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER NOT NULL,
            mm_nummer VARCHAR(50) NOT NULL,
            beschreibung TEXT NOT NULL,
            besteller_id INTEGER,
            bestellt BOOLEAN DEFAULT FALSE,
            bestellt_am DATETIME,
            pr_nummer VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (problem_id) REFERENCES problem (id) ON DELETE CASCADE,
            FOREIGN KEY (besteller_id) REFERENCES user (id) ON DELETE SET NULL
        )
    ''')
    
    # Index für bessere Performance
    cursor.execute('''
        CREATE INDEX idx_material_problem_id ON material_item (problem_id)
    ''')
    
    cursor.execute('''
        CREATE INDEX idx_material_besteller_id ON material_item (besteller_id)
    ''')
    
    conn.commit()
    print("MaterialItem-Tabelle erfolgreich erstellt.")
    
    # Zeige aktuelle Tabellen
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"Aktuelle Tabellen: {[table[0] for table in tables]}")
    
    conn.close()

if __name__ == '__main__':
    print("Erstelle MaterialItem-Tabelle...")
    create_material_table()
    print("Migration abgeschlossen.")