#!/usr/bin/env python3
"""
Erstellt 20 Beispiel-Probleme für die Wartungs-App
"""

import sys
import os
from datetime import datetime, timezone, timedelta
import random

# Füge das aktuelle Verzeichnis zum Python-Path hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Problem, User

# Beispieldaten - Exakt wie im Formular
BOHRTUERME = ["T-700", "T-46", "T-208", "T-207"]  # Exakt aus problem.html
ABTEILUNGEN = ["Elektrisch", "Mechanisch", "Anlage"]  # Exakt aus problem.html
SYSTEME = [
    "Hydraulik", "Steuerung", "Motor", "Getriebe", "Pumpe", "Kompressor",
    "Beleuchtung", "Sicherheitssystem", "Bohrkopf", "Antrieb", "Kupplung",
    "Bremse", "Ventile", "Sensoren", "Kühlung", "Schmierung", "Filter",
    "Rohrleitungen", "Dichtungen", "Lager"
]

PROBLEME = [
    "Ungewöhnliche Geräusche beim Betrieb",
    "Hydraulikflüssigkeit leckt an der Verbindung",
    "Motor startet nicht ordnungsgemäß",
    "Überhitzung bei normalem Betrieb",
    "Vibration stärker als üblich",
    "Druckabfall im System festgestellt",
    "Elektrische Verbindung zeigt Korrosion",
    "Dichtung muss ausgetauscht werden",
    "Kalibrierung der Sensoren erforderlich",
    "Schmierung unzureichend",
    "Verschleiß an beweglichen Teilen",
    "Software-Update benötigt",
    "Sicherheitsschalter reagiert nicht",
    "Temperaturregelung funktioniert nicht",
    "Pumpenleistung unter Sollwert",
    "Filtereinheit verstopft",
    "Kupplungsdefekt vermutet",
    "Anzeige zeigt falsche Werte",
    "Notabschaltung ausgelöst",
    "Wartungsintervall überschritten"
]

STATUS_OPTIONS = ["gemeldet", "in_bearbeitung", "abgearbeitet", "bestätigt"]
MASSNAHMEN = [
    "Inspektion durchgeführt",
    "Ersatzteil bestellt",
    "Reparatur abgeschlossen",
    "System neu kalibriert",
    "Wartung durchgeführt",
    "Komponente ausgetauscht",
    "Software aktualisiert",
    "Dichtung erneuert",
    "Filter gewechselt",
    "Schmierung ergänzt"
]

def create_sample_problems():
    """Erstellt 20 Beispiel-Probleme"""
    
    with app.app_context():
        print("🔧 Erstelle Beispiel-Probleme...")
        
        # Hole alle Benutzer
        users = User.query.all()
        if not users:
            print("❌ Keine Benutzer gefunden! Erstelle zuerst Benutzer.")
            return
        
        user_ids = [user.id for user in users]
        
        # Lösche alle existierenden Probleme
        Problem.query.delete()
        db.session.commit()
        print("🗑️ Alle existierenden Probleme gelöscht")
        
        problems_created = 0
        
        for i in range(20):
            # Zufällige Daten auswählen
            bohrturm = random.choice(BOHRTUERME)
            abteilung = random.choice(ABTEILUNGEN)
            system = random.choice(SYSTEME)
            problem_text = random.choice(PROBLEME)
            status = random.choice(STATUS_OPTIONS)
            
            # Zufällige Zeitstempel (letzte 30 Tage)
            days_ago = random.randint(0, 30)
            status_changed_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
            
            # Zufällige Zuweisung
            assigned_to = random.choice(user_ids) if random.random() > 0.3 else None
            besteller_id = random.choice(user_ids) if random.random() > 0.7 else None
            
            # Bestellung manchmal benötigt
            bestellung_benoetigt = random.random() > 0.7
            pr_nummer = f"PR-{random.randint(1000, 9999)}" if bestellung_benoetigt else None
            
            # Material-Details für manche Probleme
            mm_nummer = f"MM-{random.randint(100000, 999999)}" if bestellung_benoetigt else None
            teil_beschreibung = random.choice([
                "Hydraulikdichtung O-Ring 50x3mm",
                "Kugellager SKF 6205-2RS",
                "Elektromotor 3-phasig 5.5kW",
                "Drucksensor 0-250 bar",
                "Sicherheitsventil 1/2 Zoll",
                "Kupplungselement elastisch",
                "Schmierstoff 5L SAE 10W-40",
                "Filtereinsatz Hydraulik",
            ]) if bestellung_benoetigt else None
            
            # Maßnahmen für bearbeitete Probleme
            massnahmen_text = random.choice(MASSNAHMEN) if status in ['abgearbeitet', 'bestätigt'] else None
            material_liste = f"1x {teil_beschreibung}" if teil_beschreibung else None
            
            # Problem erstellen
            new_problem = Problem(
                bohrturm=bohrturm,
                abteilung=abteilung,
                system=system,
                problem=problem_text,
                status=status,
                status_changed_at=status_changed_at,
                assigned_to=assigned_to,
                besteller_id=besteller_id,
                bestellung_benoetigt=bestellung_benoetigt,
                pr_nummer=pr_nummer,
                mm_nummer=mm_nummer,
                teil_beschreibung=teil_beschreibung,
                massnahmen=massnahmen_text,
                material_liste=material_liste,
                behoben=(status in ['abgearbeitet', 'bestätigt'])
            )
            
            db.session.add(new_problem)
            problems_created += 1
            
            print(f"✅ Problem {problems_created}: {bohrturm} - {system} - {status}")
        
        # Speichern
        db.session.commit()
        print(f"\n🎉 {problems_created} Beispiel-Probleme erfolgreich erstellt!")
        
        # Statistik anzeigen
        print("\n📊 Statistik:")
        for status in STATUS_OPTIONS:
            count = Problem.query.filter_by(status=status).count()
            print(f"  {status}: {count} Probleme")
        
        print(f"\n💾 Gesamt: {Problem.query.count()} Probleme in der Datenbank")

if __name__ == "__main__":
    create_sample_problems()