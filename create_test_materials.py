#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script zum Erstellen von Test-Problemen mit Material-Bestellungen
"""

import sys
import os
from datetime import datetime, date, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# App-Pfad hinzufügen
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Problem, MaterialItem, User

def create_test_problems_with_materials():
    """Erstellt 5 Test-Probleme mit Material-Bestellungen"""
    
    with app.app_context():
        print("🔧 Erstelle Test-Probleme mit Material-Bestellungen...")
        
        # Prüfe ob Users existieren
        users = User.query.all()
        print(f"📋 Verfügbare Users: {[u.username for u in users]}")
        
        # Test-Probleme mit verschiedenen Anlagen
        test_problems = [
            {
                'anlage': 'T-700',
                'problem': 'Hydraulikpumpe defekt - Material benötigt',
                'abteilung': 'Mechanik',
                'materialien': [
                    {'mm_nummer': 'HYD-001', 'beschreibung': 'Hydraulikpumpe XYZ-123', 'menge': 1, 'einheit': 'Stück'},
                    {'mm_nummer': 'DICHT-445', 'beschreibung': 'Dichtungssatz komplett', 'menge': 1, 'einheit': 'Set'}
                ]
            },
            {
                'anlage': 'T-46',
                'problem': 'Bohrkopf verschlissen - Ersatzteile erforderlich',
                'abteilung': 'Bohrung',
                'materialien': [
                    {'mm_nummer': 'BOHR-987', 'beschreibung': 'Bohrmeißel 12 1/4"', 'menge': 2, 'einheit': 'Stück'},
                    {'mm_nummer': 'LAGER-234', 'beschreibung': 'Kugellager 6308-2RS', 'menge': 4, 'einheit': 'Stück'}
                ]
            },
            {
                'anlage': 'T-208',
                'problem': 'Spülpumpe läuft unrund - Service benötigt',
                'abteilung': 'Spülung',
                'materialien': [
                    {'mm_nummer': 'PUMP-556', 'beschreibung': 'Spülpumpen-Liner', 'menge': 2, 'einheit': 'Stück'},
                    {'mm_nummer': 'FLÜSSIG-89', 'beschreibung': 'Hydrauliköl HLP 46', 'menge': 200, 'einheit': 'Liter'}
                ]
            },
            {
                'anlage': 'T-207',
                'problem': 'Rotary Table blockiert - Reparatur notwendig',
                'abteilung': 'Antrieb',
                'materialien': [
                    {'mm_nummer': 'ROT-789', 'beschreibung': 'Rotary Table Getriebe', 'menge': 1, 'einheit': 'Stück'},
                    {'mm_nummer': 'SCHRAUB-123', 'beschreibung': 'Schraubensatz M12x80', 'menge': 20, 'einheit': 'Stück'},
                    {'mm_nummer': 'FETT-456', 'beschreibung': 'Hochtemperatur-Lagerfett', 'menge': 5, 'einheit': 'kg'}
                ]
            },
            {
                'anlage': 'T-700',
                'problem': 'Elektrische Störung im Hauptverteiler',
                'abteilung': 'Elektrik',
                'materialien': [
                    {'mm_nummer': 'ELEK-101', 'beschreibung': 'Schütz 3-polig 40A', 'menge': 2, 'einheit': 'Stück'},
                    {'mm_nummer': 'KABEL-678', 'beschreibung': 'Steuerleitung 4x1,5mm²', 'menge': 50, 'einheit': 'Meter'}
                ]
            }
        ]
        
        # Finde oder erstelle Test-User
        test_user = User.query.filter_by(username='TestUser').first()
        if not test_user:
            from werkzeug.security import generate_password_hash
            test_user = User(
                username='TestUser', 
                email='test@example.com',
                password=generate_password_hash('test123')
            )
            db.session.add(test_user)
            db.session.commit()
        
        # Finde Besteller-User
        besteller_users = {}
        for facility in ['T-700', 'T-46', 'T-208', 'T-207']:
            # Suche nach EL oder MECH für diese Anlage
            facility_code = facility.replace('-', '')  # T700, T46, etc.
            el_user = User.query.filter(User.username.like(f'{facility_code} EL%')).first()
            mech_user = User.query.filter(User.username.like(f'{facility_code} MECH%')).first()
            besteller_users[facility] = el_user or mech_user or test_user
        
        print(f"📋 Besteller-Users: {[(f, u.username) for f, u in besteller_users.items()]}")
        
        created_problems = []
        
        for i, test_data in enumerate(test_problems, 1):
            # Erstelle Problem
            problem = Problem(
                problem=test_data['problem'],
                bohrturm=test_data['anlage'],
                abteilung=test_data['abteilung'],
                system='Material-Bestellung',  # Required field
                status='in_bearbeitung',
                status_changed_at=datetime.now(timezone.utc),
                assigned_to=test_user.id
            )
            
            db.session.add(problem)
            db.session.flush()  # Um die ID zu bekommen
            
            print(f"✅ Problem #{problem.id} erstellt: {test_data['problem']} ({test_data['anlage']})")
            
            # Erstelle Material-Items für dieses Problem
            besteller = besteller_users.get(test_data['anlage'], test_user)
            
            for j, mat_data in enumerate(test_data['materialien']):
                material = MaterialItem(
                    mm_nummer=mat_data['mm_nummer'],
                    beschreibung=mat_data['beschreibung'],
                    menge=mat_data['menge'],
                    einheit=mat_data['einheit'],
                    problem_id=problem.id,
                    besteller_id=besteller.id,
                    bestellt=False,
                    # Füge Test-Daten für PR/PO/Lieferdatum hinzu
                    pr_nummer=f'PR-2025-{problem.id:03d}-{j+1:02d}' if j == 0 else None,  # Nur erstes Material hat PR
                    po_nummer=f'PO-{problem.id:04d}-{j+1}' if j <= 1 else None,  # Erste zwei haben PO
                    lieferdatum=date(2025, 10, 15 + j) if j == 0 else None  # Nur erstes hat Datum
                )
                
                db.session.add(material)
                print(f"  📦 Material: {mat_data['mm_nummer']} - {mat_data['beschreibung']}")
                print(f"      PR: {material.pr_nummer}, PO: {material.po_nummer}, Datum: {material.lieferdatum}")
            
            created_problems.append(problem)
        
        # Speichere alle Änderungen
        db.session.commit()
        print(f"\n🎉 {len(created_problems)} Test-Probleme mit Material-Bestellungen erstellt!")
        print("📋 Probleme sind im Status 'in_bearbeitung' und haben Material-Items mit:")
        print("   - PR-Nummern (erstes Material)")
        print("   - PO-Nummern (erste zwei Materialien)")
        print("   - Lieferdaten (erstes Material)")
        print("\n🔗 Öffne http://127.0.0.1:5000/problems um sie zu sehen!")

if __name__ == '__main__':
    create_test_problems_with_materials()