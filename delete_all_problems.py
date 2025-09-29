#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script zum Löschen aller Test-Probleme und Material-Items
"""

import sys
import os

# App-Pfad hinzufügen
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Problem, MaterialItem
from sqlalchemy import text

def delete_all_test_problems():
    """Löscht alle Test-Probleme und Material-Items mit Force-Delete"""
    
    with app.app_context():
        print("🗑️ Lösche alle Test-Probleme und Material-Items...")
        
        try:
            # Methode 1: Versuche normales ORM-Delete
            print("🔧 Versuche normales ORM-Delete...")
            
            # Hole alle Probleme
            all_problems = Problem.query.all()
            print(f"📋 Gefundene Probleme: {len(all_problems)}")
            
            for problem in all_problems:
                print(f"  🗑️ Problem #{problem.id}: {problem.problem} ({problem.bohrturm})")
            
            # Lösche alle Material-Items
            all_materials = MaterialItem.query.all()
            print(f"📦 Gefundene Material-Items: {len(all_materials)}")
            
            for material in all_materials:
                print(f"  🗑️ Material #{material.id}: {material.beschreibung}")
                db.session.delete(material)
            
            # Lösche alle Probleme
            for problem in all_problems:
                db.session.delete(problem)
            
            db.session.commit()
            print("✅ Normales ORM-Delete erfolgreich!")
            
        except Exception as e:
            print(f"❌ Normales ORM-Delete fehlgeschlagen: {e}")
            db.session.rollback()
            
            # Methode 2: Force-Delete mit direktem SQL
            try:
                print("🔧 Versuche Force-Delete mit direktem SQL...")
                
                with db.engine.connect() as conn:
                    # Erst alle Material-Items löschen
                    result_materials = conn.execute(text("DELETE FROM material_item"))
                    print(f"🗑️ {result_materials.rowcount} Material-Items force-gelöscht")
                    
                    # Dann alle Probleme löschen
                    result_problems = conn.execute(text("DELETE FROM problem"))
                    print(f"🗑️ {result_problems.rowcount} Probleme force-gelöscht")
                    
                    conn.commit()
                    print("✅ Force-Delete mit SQL erfolgreich!")
                    
            except Exception as force_error:
                print(f"❌ Force-Delete fehlgeschlagen: {force_error}")
                
                # Methode 3: Extreme Force-Delete - Tabellen neu erstellen
                try:
                    print("🔧 Versuche extreme Force-Delete - Tabellen neu erstellen...")
                    
                    with db.engine.connect() as conn:
                        # Lösche Tabellen komplett
                        conn.execute(text("DROP TABLE IF EXISTS material_item"))
                        conn.execute(text("DROP TABLE IF EXISTS problem"))
                        conn.commit()
                        print("🗑️ Tabellen gelöscht")
                    
                    # Erstelle Tabellen neu
                    db.create_all()
                    print("✅ Tabellen neu erstellt")
                    print("🎉 Extreme Force-Delete erfolgreich!")
                    
                except Exception as extreme_error:
                    print(f"❌ Extreme Force-Delete fehlgeschlagen: {extreme_error}")
                    return False
        
        # Prüfe Ergebnis
        remaining_problems = Problem.query.count()
        remaining_materials = MaterialItem.query.count()
        
        print(f"\n📊 Ergebnis:")
        print(f"   Verbleibende Probleme: {remaining_problems}")
        print(f"   Verbleibende Material-Items: {remaining_materials}")
        
        if remaining_problems == 0 and remaining_materials == 0:
            print("🎉 Alle Test-Daten erfolgreich gelöscht!")
            return True
        else:
            print("⚠️ Einige Daten konnten nicht gelöscht werden")
            return False

if __name__ == '__main__':
    print("🗑️ WARNUNG: Dieses Script löscht ALLE Probleme und Material-Items!")
    delete_all_test_problems()