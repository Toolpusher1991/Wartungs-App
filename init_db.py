from app import app, db, User
from werkzeug.security import generate_password_hash


def init_db():
    with app.app_context():
        # Datenbank-Tabellen erstellen
        db.create_all()
        
        # Admin-Accounts erstellen (passwörter gehashed)
        admin = User.query.filter_by(username='nils').first()
        if not admin:
            admin = User(username='nils', password=generate_password_hash('admin'), email='nils.wanning@gmail.com')
            db.session.add(admin)
        
        superadmin = User.query.filter_by(username='Admin').first()
        if not superadmin:
            superadmin = User(username='Admin', password=generate_password_hash('Admin'), email='admin@example.com')
            db.session.add(superadmin)
        
        db.session.commit()
        print("Datenbank wurde erfolgreich initialisiert!")


if __name__ == "__main__":
    init_db()