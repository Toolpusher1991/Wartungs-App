from app import app, get_responsible_user

with app.app_context():
    tests = [
        ('T-700', 'Elektrisch'),
        ('T-46', 'Mechanisch'),
        ('T-208', 'Anlage'),
        ('T-207', 'Elektrisch')
    ]
    
    print("=== Test der automatischen Zuweisung ===")
    for anlage, abteilung in tests:
        user = get_responsible_user(anlage, abteilung)
        if user:
            print(f"{anlage} + {abteilung:12} → {user.username} ({user.email})")
        else:
            print(f"{anlage} + {abteilung:12} → Nicht gefunden")