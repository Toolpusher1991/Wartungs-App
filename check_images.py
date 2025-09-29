import sqlite3

conn = sqlite3.connect('instance/problems.db')
cursor = conn.cursor()

# Prüfe alle Probleme und ihre Bilder
cursor.execute('SELECT id, problem, images FROM problem')
results = cursor.fetchall()

print(f"Alle Probleme in der Datenbank: {len(results)}")
problems_with_images = 0

for r in results:
    if r[2]:  # images Feld ist nicht leer
        problems_with_images += 1
        print(f"Problem ID {r[0]}: {r[1][:50]}...")
        print(f"  Bilder: {r[2]}")

print(f"\nProbleme mit Bildern: {problems_with_images}")

conn.close()