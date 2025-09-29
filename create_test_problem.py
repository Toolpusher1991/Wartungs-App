import sqlite3
import json

conn = sqlite3.connect('instance/problems.db')
cursor = conn.cursor()

# Erstelle ein Test-Problem mit Demo-Bildern
test_images = ['demo_image_1.jpg', 'demo_image_2.jpg']
images_json = json.dumps(test_images)

cursor.execute('''
    INSERT INTO problem (bohrturm, abteilung, system, problem, status, images)
    VALUES (?, ?, ?, ?, ?, ?)
''', ('T-700', 'Mechanisch', 'Hydraulik', 'Testproblem mit Demo-Bildern - Hydraulikleitung undicht', 'gemeldet', images_json))

conn.commit()
print("✅ Test-Problem mit Demo-Bildern erstellt!")

# Zeige das erstellte Problem
cursor.execute('SELECT id, problem, images FROM problem WHERE images IS NOT NULL')
result = cursor.fetchone()
if result:
    print(f"Problem ID {result[0]}: {result[1]}")
    print(f"Bilder: {result[2]}")

conn.close()