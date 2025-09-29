#!/usr/bin/env python3
"""
Script zum Ändern des Passworts für T700 EL
"""

from app import app, db, User
from werkzeug.security import generate_password_hash

def change_password():
    with app.app_context():
        # T700 EL User finden
        user = User.query.filter_by(username='T700 EL').first()
        
        if user:
            print(f"User gefunden: {user.username}")
            print(f"Aktuelle E-Mail: {user.email}")
            
            # Passwort auf 123456 ändern
            user.password_hash = generate_password_hash('123456')
            db.session.commit()
            
            print("✅ Passwort für T700 EL erfolgreich auf '123456' geändert")
            
            # Zur Bestätigung - Login testen
            from werkzeug.security import check_password_hash
            if check_password_hash(user.password_hash, '123456'):
                print("✅ Passwort-Verifikation erfolgreich")
            else:
                print("❌ Passwort-Verifikation fehlgeschlagen")
                
        else:
            print("❌ User 'T700 EL' nicht gefunden")
            
            # Alle User anzeigen
            all_users = User.query.all()
            print(f"\nVerfügbare User ({len(all_users)}):")
            for u in all_users:
                print(f"- {u.username}")

if __name__ == '__main__':
    change_password()