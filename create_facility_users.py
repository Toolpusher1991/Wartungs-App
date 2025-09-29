#!/usr/bin/env python3
"""
Benutzer-Setup für Wartungs-App
Erstellt systematische Benutzer für alle Anlagen und Fachbereiche
"""

from app import app, db, User
import sys

def create_facility_users():
    """Erstelle Benutzer für alle Anlagen und Fachbereiche"""
    
    with app.app_context():
        try:
            print("=== Benutzer-Setup für Wartungs-App ===\n")
            
            # 1. Bestehende Benutzer anzeigen
            all_users = User.query.all()
            print(f"Bestehende Benutzer ({len(all_users)}):")
            for user in all_users:
                print(f"  - {user.username} ({user.email})")
            
            # 2. Alle Benutzer außer nils und Admin löschen
            users_to_keep = ['nils', 'Admin']
            users_to_delete = User.query.filter(~User.username.in_(users_to_keep)).all()
            
            if users_to_delete:
                print(f"\n🗑️  Lösche {len(users_to_delete)} Benutzer:")
                for user in users_to_delete:
                    print(f"  - Lösche: {user.username}")
                    db.session.delete(user)
                
                db.session.commit()
                print("✅ Alte Benutzer erfolgreich gelöscht\n")
            
            # 3. Neue Benutzer-Struktur definieren
            anlagen = ['T700', 'T46', 'T208', 'T207']
            fachbereiche = [
                ('EL', 'Elektrisch'),
                ('MECH', 'Mechanisch'), 
                ('TP', 'Toolpusher'),
                ('RSC', 'Rig Supply Coordinator')
            ]
            
            neue_benutzer = []
            
            # 4. Für jede Anlage alle Fachbereiche erstellen
            for anlage in anlagen:
                for kuerzel, vollname in fachbereiche:
                    username = f"{anlage} {kuerzel}"
                    email = f"{anlage}{kuerzel}@Test.com"
                    
                    # Prüfen ob Benutzer bereits existiert
                    existing_user = User.query.filter_by(username=username).first()
                    if not existing_user:
                        user = User(
                            username=username,
                            email=email,
                            password="default_password"  # In Produktion: echtes Hashing
                        )
                        neue_benutzer.append(user)
                        db.session.add(user)
            
            # 5. Alle neuen Benutzer speichern
            if neue_benutzer:
                db.session.commit()
                print(f"✅ {len(neue_benutzer)} neue Benutzer erstellt:")
                
                # Gruppiert nach Anlage anzeigen
                for anlage in anlagen:
                    print(f"\n📍 {anlage}:")
                    for kuerzel, vollname in fachbereiche:
                        username = f"{anlage} {kuerzel}"
                        email = f"{anlage}{kuerzel}@Test.com"
                        print(f"  • {username:12} → {email:20} ({vollname})")
            
            # 6. Finale Übersicht
            final_users = User.query.order_by(User.username).all()
            print(f"\n=== Finale Benutzer-Übersicht ({len(final_users)} Benutzer) ===")
            
            # Admins
            admin_users = [u for u in final_users if u.username in ['nils', 'Admin']]
            if admin_users:
                print("\n👑 Administratoren:")
                for user in admin_users:
                    print(f"  • {user.username:15} → {user.email}")
            
            # Nach Anlage gruppiert
            for anlage in anlagen:
                anlage_users = [u for u in final_users if u.username.startswith(anlage)]
                if anlage_users:
                    print(f"\n🏭 {anlage}:")
                    for user in sorted(anlage_users, key=lambda x: x.username):
                        fachbereich = user.username.split(' ')[-1] if ' ' in user.username else ''
                        vollname = next((v for k, v in fachbereiche if k == fachbereich), fachbereich)
                        print(f"  • {user.username:12} → {user.email:20} ({vollname})")
            
            print(f"\n✅ Setup abgeschlossen! {len(final_users)} Benutzer sind jetzt verfügbar.")
            print("\n📋 Struktur:")
            print("   • nils & Admin (Administratoren)")
            print("   • 4 Anlagen: T700, T46, T208, T207")
            print("   • 4 Fachbereiche je Anlage: EL, MECH, TP, RSC")
            print("   • Email-Format: [Anlage][Fachbereich]@Test.com")
            
        except Exception as e:
            print(f"❌ Fehler beim Setup: {e}")
            db.session.rollback()
            return False
    
    return True

if __name__ == '__main__':
    success = create_facility_users()
    sys.exit(0 if success else 1)