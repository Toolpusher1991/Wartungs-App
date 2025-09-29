from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message  # 📧 REAL EMAIL: Aktiviert für echten Email-Versand
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timezone, timedelta
from sqlalchemy import case
import os
import json
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image

# App-Initialisierung
app = Flask(__name__)
# Load environment variables from .env file for local development if present
load_dotenv()
# Use environment variables for secrets in production; provide dev-friendly defaults
app.secret_key = os.environ.get('WARTUNG_APP_SECRET', 'dev-secret-key')

# Disable template caching for development
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///problems.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# CSRF-Schutz temporär deaktiviert (TODO: Token zu Formularen hinzufügen)
# csrf = CSRFProtect(app)

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/wartungsapp.log'),
        logging.StreamHandler()
    ]
)

# Rate-Limiting für Login-Versuche (einfache Implementation)
login_attempts = {}

# E-Mail-Konfiguration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'nils.wanning@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
app.config['MAIL_SUPPRESS_SEND'] = os.environ.get('MAIL_SUPPRESS_SEND', 'False') == 'True'

# Upload-Konfiguration
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Initialize extensions
mail = Mail(app)  # 📧 REAL EMAIL: Aktiviert für echten Email-Versand
db = SQLAlchemy(app)

# Stelle sicher, dass der Upload-Ordner existiert
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.context_processor
def inject_current_year():
    """Provide the current year to all templates as `current_year`."""
    return {'current_year': datetime.now(timezone.utc).year}

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bohrturm = db.Column(db.String(100), nullable=False)
    abteilung = db.Column(db.String(50), nullable=False)
    system = db.Column(db.String(100), nullable=False)
    problem = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='gemeldet')
    loeschen_kommentar = db.Column(db.String(300))
    behoben = db.Column(db.Boolean, default=False)
    bestellung_benoetigt = db.Column(db.Boolean, default=False)
    pr_nummer = db.Column(db.String(50))
    verantwortlicher = db.Column(db.String(100))  # Legacy field - keep for backward compatibility
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_user = db.relationship('User', foreign_keys=[assigned_to], backref=db.backref('assigned_problems', lazy=True))
    status_changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    massnahmen = db.Column(db.String(500))
    material_liste = db.Column(db.String(500))
    images = db.Column(db.Text)  # JSON-String für Bildpfade
    mm_nummer = db.Column(db.String(100))  # MM-Nummer für Material-Bestellung
    teil_beschreibung = db.Column(db.String(200))  # Optionale Teilbeschreibung
    besteller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Wer die Bestellung auslöst
    besteller_user = db.relationship('User', foreign_keys=[besteller_id], backref=db.backref('bestellungen', lazy=True))
    # Bestellbestätigung Felder
    bestellung_bestaetigt = db.Column(db.Boolean, default=False)  # Besteller hat Bestellung bestätigt
    pr_nummer = db.Column(db.String(50))  # PR-Nummer nach Bestellbestätigung
    lieferdatum = db.Column(db.Date)  # Erwartetes Lieferdatum
    bestellung_bestaetigt_am = db.Column(db.DateTime)  # Zeitpunkt der Bestätigung
    progress_updates = db.Column(db.Text)  # JSON-String für Fortschritt-Updates
    
    @property
    def image_list(self):
        """Gibt eine Liste der Bildpfade zurück"""
        if self.images:
            return json.loads(self.images)
        return []
    
    @image_list.setter
    def image_list(self, value):
        """Setzt die Bildliste als JSON-String"""
        self.images = json.dumps(value) if value else None
    
    @property
    def progress_update_list(self):
        """Gibt eine Liste der Fortschritt-Updates zurück"""
        if self.progress_updates:
            return json.loads(self.progress_updates)
        return []
    
    @progress_update_list.setter
    def progress_update_list(self, value):
        """Setzt die Update-Liste als JSON-String"""
        self.progress_updates = json.dumps(value) if value else None

    @property
    def material_items(self):
        """Gibt eine Liste aller Material-Items für dieses Problem zurück"""
        return MaterialItem.query.filter_by(problem_id=self.id).all()


# Material-Katalog für häufig verwendete Teile
class MaterialCatalog(db.Model):
    """Katalog für Standard-Materialien"""
    id = db.Column(db.Integer, primary_key=True)
    mm_nummer = db.Column(db.String(100), unique=True, nullable=False)
    beschreibung = db.Column(db.String(300), nullable=False)
    kategorie = db.Column(db.String(100))  # z.B. "Hydraulik", "Elektrik", "Mechanik"
    einheit = db.Column(db.String(20), default='Stück')  # Stück, Liter, Meter, etc.
    standard_lieferant = db.Column(db.String(100))
    durchschnittspreis = db.Column(db.Float)
    lagerbestand = db.Column(db.Integer, default=0)
    mindestbestand = db.Column(db.Integer, default=1)
    haeufig_verwendet = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class MaterialItem(db.Model):
    """Model für einzelne Material-Items pro Problem"""
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey('problem.id', ondelete='CASCADE'), nullable=False)
    mm_nummer = db.Column(db.String(100), nullable=False)
    beschreibung = db.Column(db.String(200), nullable=False)
    menge = db.Column(db.Integer, default=1)
    einheit = db.Column(db.String(20), default='Stück')
    besteller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    bestellt = db.Column(db.Boolean, default=False)
    bestellt_am = db.Column(db.DateTime)
    pr_nummer = db.Column(db.String(50))
    po_nummer = db.Column(db.String(50))  # Purchase Order Nummer
    lieferdatum = db.Column(db.Date)      # Geplantes Lieferdatum
    kosten = db.Column(db.Float)
    lieferant = db.Column(db.String(100))
    
    # Relationships
    problem = db.relationship('Problem', backref=db.backref('materials', lazy=True, cascade='all, delete-orphan'))
    besteller_user = db.relationship('User', foreign_keys=[besteller_id])


def allowed_file(filename):
    """Überprüft, ob die Datei einen erlaubten Dateityp hat"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def optimize_image(filepath, max_size=(1920, 1080), quality=85):
    """Optimiert Bilder für bessere Performance und Speicherplatz"""
    try:
        with Image.open(filepath) as img:
            # Konvertiere zu RGB falls RGBA (für JPEG)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Größe anpassen falls zu groß
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Als JPEG mit Qualitätsoptimierung speichern
            img.save(filepath, 'JPEG', quality=quality, optimize=True)
    except Exception as e:
        logging.warning(f"Bildoptimierung fehlgeschlagen für {filepath}: {e}")


def save_uploaded_files(files):
    """Speichert hochgeladene Dateien und gibt Liste der Dateinamen zurück"""
    saved_files = []
    for file in files:
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Eindeutigen Dateinamen erstellen
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Bildoptimierung für bessere Performance
            if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                optimize_image(filepath)
            
            saved_files.append(filename)
    return saved_files


class OneTimeToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(128), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    used = db.Column(db.Boolean, default=False)

# Admin-Account erstellen
def create_admin():
    admin = User.query.filter_by(username='nils').first()
    if not admin:
        admin = User(username='nils', password=generate_password_hash('admin'), email='nils.wanning@gmail.com')
        db.session.add(admin)
    
    superadmin = User.query.filter_by(username='Admin').first()
    if not superadmin:
        superadmin = User(username='Admin', password=generate_password_hash('Admin'), email='admin@example.com')
        db.session.add(superadmin)
    db.session.commit()

def get_responsible_user(anlage, abteilung):
    """
    Automatische Zuweisung des Verantwortlichen basierend auf Anlage und Abteilung
    
    Args:
        anlage: z.B. 'T-700', 'T-46', 'T-208', 'T-207'
        abteilung: z.B. 'Elektrisch', 'Mechanisch', 'Anlage'
    
    Returns:
        User object oder None
    """
    # Mapping von Abteilung zu Fachbereich-Kürzel
    abteilung_mapping = {
        'Elektrisch': 'EL',
        'Mechanisch': 'MECH',
        'Anlage': 'TP'  # Toolpusher für allgemeine Anlagen-Probleme
    }
    
    # Anlage normalisieren (entferne Bindestriche für Username)
    anlage_clean = anlage.replace('-', '')  # T-700 -> T700
    
    # Fachbereich-Kürzel ermitteln
    fachbereich = abteilung_mapping.get(abteilung)
    if not fachbereich:
        return None
    
    # Username zusammensetzen: T700 EL, T46 MECH, etc.
    username = f"{anlage_clean} {fachbereich}"
    
    # Benutzer suchen
    user = User.query.filter_by(username=username).first()
    return user

def get_user_facility(username):
    """
    Ermittelt die Anlage eines Benutzers basierend auf seinem Username
    
    Args:
        username: z.B. 'T700 EL', 'T46 MECH', 'nils', 'Admin'
    
    Returns:
        Anlage als String (z.B. 'T-700') oder None für Admins
    """
    if username in ['nils', 'Admin']:
        return None  # Admins haben Zugriff auf alle Anlagen
    
    # Username format: "T700 EL", "T46 MECH", etc.
    parts = username.split(' ')
    if len(parts) >= 2:
        facility_code = parts[0]  # z.B. "T700"
        # Formatiere zu Standard-Anlagen-Format: T700 -> T-700
        if facility_code.startswith('T') and facility_code[1:].isdigit():
            return f"T-{facility_code[1:]}"
    
    return None

def can_edit_facility(username, facility):
    """
    Prüft ob ein Benutzer eine bestimmte Anlage bearbeiten darf
    
    Args:
        username: Benutzername
        facility: Anlagen-Code (z.B. 'T-700')
    
    Returns:
        True wenn Bearbeitung erlaubt, False sonst
    """
    if username in ['nils', 'Admin']:
        return True  # Admins dürfen alles
    
    user_facility = get_user_facility(username)
    return user_facility == facility

def get_rsc_for_facility(facility):
    """Ermittelt den RSC (Responsible Site Coordinator) für eine Anlage"""
    print(f"🔍 DEBUG get_rsc_for_facility: Suche RSC für Anlage '{facility}'")
    
    # RSC-Zuordnung basierend auf Anlagen-Namen - suche direkt nach RSC-User
    rsc_mapping = {
        'T-700': ['T700 RSC'],     # T-700 RSC 
        'T-46': ['T46 RSC'],       # T-46 RSC
        'T-208': ['T208 RSC'],     # T-208 RSC  
        'T-207': ['T207 RSC']      # T-207 RSC
    }
    
    rsc_users = rsc_mapping.get(facility, [])
    print(f"🔍 DEBUG get_rsc_for_facility: RSC-Kandidaten für '{facility}': {rsc_users}")
    
    # Suche nach verfügbaren RSC-Usern
    for username in rsc_users:
        print(f"🔍 DEBUG get_rsc_for_facility: Suche User '{username}'...")
        user = User.query.filter_by(username=username).first()
        if user:
            print(f"🔍 DEBUG get_rsc_for_facility: ✅ RSC gefunden: {user.username} ({user.email})")
            return user
        else:
            print(f"🔍 DEBUG get_rsc_for_facility: ❌ User '{username}' nicht in DB gefunden")
    
    # Fallback: Erster Admin wenn kein RSC gefunden
    print(f"🔍 DEBUG get_rsc_for_facility: Kein RSC gefunden, verwende Admin-Fallback")
    admin_user = User.query.filter(User.username.in_(['nils', 'Admin'])).first()
    if admin_user:
        print(f"🔍 DEBUG get_rsc_for_facility: Admin-Fallback: {admin_user.username}")
    else:
        print(f"🔍 DEBUG get_rsc_for_facility: ❌ Kein Admin gefunden!")
    return admin_user

def can_manage_material_orders(username, facility):
    """
    Prüft ob ein Benutzer Material-Bestellungen (PR, PO, Lieferdatum) verwalten darf
    
    NUR RSCs der entsprechenden Anlage und Admins dürfen:
    - PR-Nummern eintragen
    - PO-Nummern eintragen  
    - Lieferdatum eintragen
    - Bestellung als bestellt markieren
    
    Args:
        username: Benutzername
        facility: Anlagen-Code (z.B. 'T-700')
    
    Returns:
        True wenn Material-Management erlaubt, False sonst
    """
    # Admins dürfen alles
    if username in ['nils', 'Admin']:
        return True
    
    # Prüfe ob der User der RSC für diese Anlage ist
    rsc_user = get_rsc_for_facility(facility)
    if rsc_user and rsc_user.username == username:
        return True
    
    return False

# E-Mail-Funktionen
def send_problem_assignment_email(user, problem):
    """Lokaler Email-Bot: Speichert Problem-Zuweisungs-Email lokal (keine Google Mail)"""
    try:
        subject = f"Neues Problem zugewiesen: {problem.bohrturm} - {problem.system}"
        
        # HTML-E-Mail-Template
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #1e3a8a 0%, #374151 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">🔧 Neues Problem zugewiesen</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Wartungs-App Benachrichtigung</p>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #1e3a8a;">
                    <h3 style="color: #1e3a8a; margin-top: 0;">Hallo {user.username},</h3>
                    <p>Ihnen wurde ein neues Problem zur Bearbeitung zugewiesen:</p>
                </div>
                
                <div style="background: white; border: 1px solid #dee2e6; border-radius: 8px; margin: 20px 0; overflow: hidden;">
                    <div style="background: #1e3a8a; color: white; padding: 15px;">
                        <h3 style="margin: 0;">📋 Problem-Details</h3>
                    </div>
                    <div style="padding: 20px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a; width: 120px;">🏗️ Anlage:</td>
                                <td style="padding: 8px 0;">{problem.bohrturm}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a;">🏢 Abteilung:</td>
                                <td style="padding: 8px 0;">{problem.abteilung}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a;">⚙️ System:</td>
                                <td style="padding: 8px 0;">{problem.system}</td>
                            </tr>
                        </table>
                        <hr style="margin: 15px 0; border: none; border-top: 1px solid #dee2e6;">
                        <div>
                            <p style="font-weight: bold; color: #1e3a8a; margin-bottom: 10px;">⚠️ Problembeschreibung:</p>
                            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px;">
                                {problem.problem}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://192.168.188.20:5000/problem" 
                       style="background: #1e3a8a; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                        🔗 Neues Problem melden
                    </a>
                </div>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; font-size: 12px; color: #6c757d;">
                    <p style="margin: 0;">Diese E-Mail wurde automatisch von der Wartungs-App gesendet.</p>
                    <p style="margin: 5px 0 0 0;">Bitte nicht auf diese E-Mail antworten.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Text-Version als Fallback
        text_body = f"""
Neues Problem zugewiesen: {problem.bohrturm} - {problem.system}

Hallo {user.username},

Ihnen wurde ein neues Problem zur Bearbeitung zugewiesen:

Anlage: {problem.bohrturm}
Abteilung: {problem.abteilung}
System: {problem.system}

Problembeschreibung:
{problem.problem}

Bitte loggen Sie sich in die Wartungs-App ein, um ein neues Problem zu melden:
http://192.168.188.20:5000/problem

Diese E-Mail wurde automatisch gesendet.
        """
        
        # 🤖 EMAIL-BOT: Lokale Email-Speicherung (kein Google Mail)
        return save_email_locally(
            recipient=user.email,
            recipient_name=user.username,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            email_type="problem_assignment",
            problem_id=problem.id
        )
        
    except Exception as e:
        logging.error(f"Fehler beim Senden der Problem-Zuweisungs-E-Mail an {user.email}: {e}")
        return False

def send_problem_notification_email(user, problem, responsible_user):
    """Benachrichtigt interessierte Parteien über Problem-Übernahme"""
    try:
        subject = f"Problem wird bearbeitet: {problem.bohrturm} - {problem.system}"
        
        # HTML-E-Mail-Template für Interested Parties
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #1e3a8a 0%, #374151 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">🔧 Problem-Update</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Wartungs-App Benachrichtigung</p>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #1e3a8a;">
                    <h3 style="color: #1e3a8a; margin-top: 0;">Hallo {user.username},</h3>
                    <p>Ein Problem, das Sie interessieren könnte, wird nun bearbeitet:</p>
                </div>
                
                <div style="background: white; border: 1px solid #dee2e6; border-radius: 8px; margin: 20px 0; overflow: hidden;">
                    <div style="background: #17a2b8; color: white; padding: 15px;">
                        <h3 style="margin: 0;">📋 Problem-Details</h3>
                    </div>
                    <div style="padding: 20px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a; width: 120px;">🏗️ Anlage:</td>
                                <td style="padding: 8px 0;">{problem.bohrturm}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a;">🏢 Abteilung:</td>
                                <td style="padding: 8px 0;">{problem.abteilung}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a;">⚙️ System:</td>
                                <td style="padding: 8px 0;">{problem.system}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a;">👤 Bearbeiter:</td>
                                <td style="padding: 8px 0;">{responsible_user}</td>
                            </tr>
                        </table>
                        <hr style="margin: 15px 0; border: none; border-top: 1px solid #dee2e6;">
                        <div>
                            <p style="font-weight: bold; color: #1e3a8a; margin-bottom: 10px;">⚠️ Problembeschreibung:</p>
                            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px;">
                                {problem.problem}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; font-size: 12px; color: #6c757d;">
                    <p style="margin: 0;">Diese Benachrichtigung wurde automatisch von der Wartungs-App gesendet.</p>
                    <p style="margin: 5px 0 0 0;">Sie wurden als interessierte Partei für dieses Problem informiert.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # 🤖 EMAIL-BOT: Lokale Email-Speicherung (kein Google Mail)
        return save_email_locally(
            recipient=user.email,
            recipient_name=user.username,
            subject=subject,
            html_body=html_body,
            text_body=f"Problem wird bearbeitet: {problem.bohrturm} - {problem.system}\n\nBearbeiter: {responsible_user}\n\nProblem: {problem.problem}",
            email_type="problem_notification",
            problem_id=problem.id
        )
        
    except Exception as e:
        logging.error(f"Fehler beim Senden der Problem-Benachrichtigung an {user.email}: {e}")
        return False

def send_and_save_email(recipient, recipient_name, subject, html_body, text_body, email_type, problem_id=None):
    """📧 TEST-MODUS: Alle E-Mails gehen an Nils zur Kontrolle"""
    email_sent = False
    email_saved = False
    
    # TEST-MODUS: Alle E-Mails an Test-Adresse umleiten
    original_recipient = recipient
    original_name = recipient_name
    recipient = "nils.wanning@gmail.com"  # Test-Empfänger
    recipient_name = "Nils (Test)"
    
    # Subject mit Original-Empfänger erweitern für Tests
    subject = f"[TEST für {original_name}] {subject}"
    print(f"🔍 DEBUG: E-Mail geht an Test-Adresse: {recipient} (Original: {original_name})")
    
    # 1. ECHTE EMAIL VERSENDEN (Test-Modus mit Gmail)
    if app.config.get('MAIL_PASSWORD'):
        try:
            msg = Message(
                subject=subject,
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[recipient]
            )
            msg.body = text_body
            msg.html = html_body
            
            mail.send(msg)
            email_sent = True
            logging.info(f"[EMAIL] REAL EMAIL SENT: {recipient} ({recipient_name}) - {subject}")
            
        except Exception as e:
            logging.error(f"[EMAIL] REAL EMAIL FAILED: {recipient} - {e}")
    else:
        logging.warning("⚠️ MAIL_PASSWORD not set - skipping real email send")
    
    # 2. LOKALE SPEICHERUNG (Email-Bot)
    try:
        from datetime import datetime
        import json
        import os
        
        # Email-Verzeichnis sicherstellen
        email_dir = os.path.join(os.path.dirname(__file__), 'logs', 'emails')
        os.makedirs(email_dir, exist_ok=True)
        
        # Timestamp für Dateinamen
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_{email_type}_{problem_id or 'general'}.json"
        
        # Email-Daten strukturieren
        email_data = {
            "timestamp": timestamp.isoformat(),
            "recipient": recipient,
            "recipient_name": recipient_name,
            "subject": subject,
            "email_type": email_type,
            "problem_id": problem_id,
            "html_body": html_body,
            "text_body": text_body,
            "status": "sent_and_saved" if email_sent else "saved_only",
            "real_email_sent": email_sent,
            "sent_via": "hybrid_system_v1.0"
        }
        
        # Email als JSON speichern
        json_file = os.path.join(email_dir, filename)
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(email_data, f, indent=2, ensure_ascii=False)
        
        # HTML-Version für Browser-Vorschau speichern
        html_file = os.path.join(email_dir, f"{timestamp_str}_{email_type}_{problem_id or 'general'}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_body)
        
        email_saved = True
        status_msg = "[EMAIL] REAL EMAIL + LOCAL SAVE" if email_sent else "[SAVE] LOCAL SAVE ONLY"
        logging.info(f"{status_msg}: {recipient} ({recipient_name}) - {subject}")
        
    except Exception as e:
        logging.error(f"[SAVE] LOCAL SAVE FAILED: {e}")
    
    # Erfolgreich wenn mindestens eine Methode funktioniert hat
    return email_sent or email_saved

# Alias für Rückwärtskompatibilität  
def save_email_locally(recipient, recipient_name, subject, html_body, text_body, email_type, problem_id=None):
    """Alias für die hybride Email-Funktion"""
    return send_and_save_email(recipient, recipient_name, subject, html_body, text_body, email_type, problem_id)

def send_material_request_email(rsc_user, problem, material_item, requester_name):
    """📧 RSC-Benachrichtigung: Material wurde angefordert - bitte bestellen"""
    try:
        subject = f"🛒 Material-Bestellung erforderlich: {problem.bohrturm} - {material_item.mm_nummer}"
        
        # HTML-E-Mail-Template
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">🚨 Material-Bestellung erforderlich</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">RSC-Benachrichtigung</p>
                </div>
                
                <div style="background: #fee2e2; padding: 20px; border-radius: 8px; border-left: 4px solid #dc2626;">
                    <h3 style="color: #991b1b; margin-top: 0;">Hallo {rsc_user.username},</h3>
                    <p>Für ein Problem wurde <strong>Material angefordert</strong> - bitte die Bestellung veranlassen und nach Lieferung PR-Nummer + Lieferdatum eintragen:</p>
                </div>
                
                <div style="background: white; border: 1px solid #dc2626; border-radius: 8px; margin: 20px 0; overflow: hidden;">
                    <div style="background: #dc2626; color: white; padding: 15px;">
                        <h3 style="margin: 0;">🛒 Material-Details</h3>
                    </div>
                    <div style="padding: 20px;">
                        <div style="margin-bottom: 15px;">
                            <span style="font-weight: bold; color: #991b1b;">📊 MM-Nummer:</span>
                            <span style="background: #dc2626; color: white; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 16px; margin-left: 10px;">{material_item.mm_nummer}</span>
                        </div>
                        <div style="margin-bottom: 15px;">
                            <span style="font-weight: bold; color: #991b1b;">🏷️ Beschreibung:</span>
                            <div style="background: #fee2e2; border: 1px solid #fca5a5; border-radius: 5px; padding: 10px; margin-top: 5px;">
                                {material_item.beschreibung}
                            </div>
                        </div>
                        <div style="margin-bottom: 15px;">
                            <span style="font-weight: bold; color: #991b1b;">📦 Menge:</span>
                            <span style="background: #059669; color: white; padding: 2px 6px; border-radius: 3px; margin-left: 5px;">{material_item.menge} {material_item.einheit}</span>
                        </div>
                    </div>
                </div>

                <div style="background: white; border: 1px solid #d1d5db; border-radius: 8px; margin: 20px 0; overflow: hidden;">
                    <div style="background: #f3f4f6; color: #374151; padding: 15px;">
                        <h3 style="margin: 0;">📋 Problem-Details</h3>
                    </div>
                    <div style="padding: 20px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #991b1b; width: 120px;">🏗️ Anlage:</td>
                                <td style="padding: 8px 0;">{problem.bohrturm}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #991b1b;">🏢 Abteilung:</td>
                                <td style="padding: 8px 0;">{problem.abteilung}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #991b1b;">⚙️ System:</td>
                                <td style="padding: 8px 0;">{problem.system}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #991b1b;">👤 Angefordert von:</td>
                                <td style="padding: 8px 0;">{requester_name}</td>
                            </tr>
                        </table>
                        <hr style="margin: 15px 0; border: none; border-top: 1px solid #dee2e6;">
                        <div>
                            <p style="font-weight: bold; color: #991b1b; margin-bottom: 10px;">⚠️ Problembeschreibung:</p>
                            <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 5px; padding: 15px;">
                                {problem.problem}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div style="background: #fef3c7; padding: 20px; border-radius: 8px; border-left: 4px solid #f59e0b; margin: 20px 0;">
                    <h3 style="color: #92400e; margin-top: 0;">📝 Aufgaben für RSC:</h3>
                    <ol style="margin: 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><strong>Material bestellen</strong> über SAP/ERP-System</li>
                        <li style="margin-bottom: 8px;"><strong>PR-Nummer</strong> nach Bestellung eintragen</li>
                        <li style="margin-bottom: 8px;"><strong>Lieferdatum</strong> nach Wareneingang aktualisieren</li>
                        <li><strong>Status</strong> auf "Geliefert" setzen</li>
                    </ol>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://192.168.188.20:5000/problems#detailModal{problem.id}-material" 
                       style="background: #dc2626; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-bottom: 15px;">
                        📝 PR-Nummer & Lieferdatum eintragen
                    </a>
                    <br>
                    <a href="http://192.168.188.20:5000/problems" 
                       style="background: #6b7280; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: normal; display: inline-block;">
                        📋 Alle Probleme anzeigen
                    </a>
                </div>
                
                <div style="background: #fef3c7; padding: 15px; border-radius: 5px; text-align: center; font-size: 12px; color: #92400e;">
                    <p style="margin: 0;">Diese E-Mail wurde automatisch von der Wartungs-App gesendet.</p>
                    <p style="margin: 5px 0 0 0;">Bitte nicht auf diese E-Mail antworten.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Text-Version als Fallback
        text_body = f"""
🚨 Material-Bestellung erforderlich: {problem.bohrturm} - {material_item.mm_nummer}

Hallo {rsc_user.username},

MATERIAL-DETAILS:
- MM-Nummer: {material_item.mm_nummer}
- Beschreibung: {material_item.beschreibung}
- Menge: {material_item.menge} {material_item.einheit}

PROBLEM-DETAILS:
- Anlage: {problem.bohrturm}
- Abteilung: {problem.abteilung}
- System: {problem.system}
- Angefordert von: {requester_name}

Problembeschreibung:
{problem.problem}

AUFGABEN FÜR RSC:
1. Material bestellen über SAP/ERP-System
2. PR-Nummer nach Bestellung eintragen
3. Lieferdatum nach Wareneingang aktualisieren
4. Status auf "Geliefert" setzen

PR-Nummer & Lieferdatum eintragen:
http://192.168.188.20:5000/problems#detailModal{problem.id}-material

Diese E-Mail wurde automatisch gesendet.
        """
        
        # 🤖 EMAIL-BOT: Lokale Email-Speicherung
        return save_email_locally(
            recipient=rsc_user.email,
            recipient_name=rsc_user.username,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            email_type="material_request",
            problem_id=problem.id
        )
        
    except Exception as e:
        logging.error(f"Fehler beim Senden der Material-Anfrage-E-Mail an {rsc_user.email}: {e}")
        return False

def send_material_order_email(besteller_user, problem, bearbeiter_name):
    """Lokaler Email-Bot: Speichert E-Mail-Benachrichtigung lokal (keine Google Mail)"""
    try:
        subject = f"Material-Bestellung angefordert: {problem.bohrturm} - {problem.system}"
        
        # HTML-E-Mail-Template
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">🛒 Material-Bestellung angefordert</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Wartungs-App Benachrichtigung</p>
                </div>
                
                <div style="background: #fff3cd; padding: 20px; border-radius: 8px; border-left: 4px solid #f59e0b;">
                    <h3 style="color: #d97706; margin-top: 0;">Hallo {besteller_user.username},</h3>
                    <p>Für ein Problem wurde eine Material-Bestellung angefordert und Sie wurden als Besteller ausgewählt:</p>
                </div>
                
                <div style="background: white; border: 1px solid #dee2e6; border-radius: 8px; margin: 20px 0; overflow: hidden;">
                    <div style="background: #f59e0b; color: white; padding: 15px;">
                        <h3 style="margin: 0;">📋 Problem-Details</h3>
                    </div>
                    <div style="padding: 20px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #d97706; width: 120px;">🏗️ Anlage:</td>
                                <td style="padding: 8px 0;">{problem.bohrturm}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #d97706;">🏢 Abteilung:</td>
                                <td style="padding: 8px 0;">{problem.abteilung}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #d97706;">⚙️ System:</td>
                                <td style="padding: 8px 0;">{problem.system}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #d97706;">👤 Bearbeiter:</td>
                                <td style="padding: 8px 0;">{bearbeiter_name}</td>
                            </tr>
                        </table>
                        <hr style="margin: 15px 0; border: none; border-top: 1px solid #dee2e6;">
                        <div>
                            <p style="font-weight: bold; color: #d97706; margin-bottom: 10px;">⚠️ Problembeschreibung:</p>
                            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px;">
                                {problem.problem}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div style="background: white; border: 1px solid #f59e0b; border-radius: 8px; margin: 20px 0; overflow: hidden;">
                    <div style="background: #f59e0b; color: white; padding: 15px;">
                        <h3 style="margin: 0;">🛒 Material-Bestellung Details</h3>
                    </div>
                    <div style="padding: 20px;">"""
        
        if problem.mm_nummer:
            html_body += f"""
                        <div style="margin-bottom: 15px;">
                            <span style="font-weight: bold; color: #d97706;">📊 MM-Nummer:</span>
                            <span style="background: #f59e0b; color: white; padding: 4px 8px; border-radius: 4px; font-family: monospace;">{problem.mm_nummer}</span>
                        </div>"""
        
        if problem.teil_beschreibung:
            html_body += f"""
                        <div style="margin-bottom: 15px;">
                            <span style="font-weight: bold; color: #d97706;">🏷️ Teil-Beschreibung:</span>
                            <div style="background: #fef3c7; border: 1px solid #f59e0b; border-radius: 5px; padding: 10px; margin-top: 5px;">
                                {problem.teil_beschreibung}
                            </div>
                        </div>"""
        
        if problem.massnahmen:
            html_body += f"""
                        <div style="margin-bottom: 15px;">
                            <span style="font-weight: bold; color: #d97706;">🔧 Geplante Maßnahmen:</span>
                            <div style="background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 5px; padding: 10px; margin-top: 5px;">
                                {problem.massnahmen}
                            </div>
                        </div>"""
        
        html_body += f"""
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://192.168.188.20:5000/confirm_order/{problem.id}" 
                       style="background: #f59e0b; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-bottom: 15px;">
                        ✅ Bestellung jetzt bestätigen
                    </a>
                    <br>
                    <a href="http://192.168.188.20:5000/problem" 
                       style="background: #6b7280; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: normal; display: inline-block;">
                        📋 Neues Problem melden
                    </a>
                </div>
                
                <div style="background: #fef3c7; padding: 15px; border-radius: 5px; text-align: center; font-size: 12px; color: #92400e;">
                    <p style="margin: 0;">Diese E-Mail wurde automatisch von der Wartungs-App gesendet.</p>
                    <p style="margin: 5px 0 0 0;">Bitte nicht auf diese E-Mail antworten.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Text-Version als Fallback
        text_body = f"""
Material-Bestellung angefordert: {problem.bohrturm} - {problem.system}

Hallo {besteller_user.username},

Für ein Problem wurde eine Material-Bestellung angefordert und Sie wurden als Besteller ausgewählt:

Anlage: {problem.bohrturm}
Abteilung: {problem.abteilung}
System: {problem.system}
Bearbeiter: {bearbeiter_name}

Problembeschreibung:
{problem.problem}

Material-Bestellung Details:"""
        
        if problem.mm_nummer:
            text_body += f"\nMM-Nummer: {problem.mm_nummer}"
        if problem.teil_beschreibung:
            text_body += f"\nTeil-Beschreibung: {problem.teil_beschreibung}"
        if problem.massnahmen:
            text_body += f"\nGeplante Maßnahmen: {problem.massnahmen}"
        
        text_body += f"""

BESTELLUNG BESTÄTIGEN:
http://192.168.188.20:5000/confirm_order/{problem.id}

Neues Problem melden:
http://192.168.188.20:5000/problem

Diese E-Mail wurde automatisch gesendet.
        """
        
        # 🤖 EMAIL-BOT: Lokale Email-Speicherung (kein Google Mail)
        return save_email_locally(
            recipient=besteller_user.email,
            recipient_name=besteller_user.username,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            email_type="material_order",
            problem_id=problem.id
        )
        
    except Exception as e:
        logging.error(f"Fehler beim Senden der Material-Bestellungs-E-Mail an {besteller_user.email}: {e}")
        return False

def send_problem_completion_email(admin, problem, kommentar):
    """Lokaler Email-Bot: Speichert Admin-Benachrichtigung lokal (keine Google Mail)"""
    try:
        subject = f"Problem abgearbeitet: {problem.bohrturm} - {problem.system}"
        
        # HTML-E-Mail-Template für abgearbeitete Probleme
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #059669 0%, #065f46 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">✅ Problem abgearbeitet</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Bereit zur Admin-Prüfung</p>
                </div>
                
                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; border-left: 4px solid #059669;">
                    <h3 style="color: #059669; margin-top: 0;">Hallo {admin.username},</h3>
                    <p>Ein Problem wurde als abgearbeitet markiert und wartet auf Ihre Prüfung:</p>
                </div>
                
                <div style="background: white; border: 1px solid #dee2e6; border-radius: 8px; margin: 20px 0; overflow: hidden;">
                    <div style="background: #059669; color: white; padding: 15px;">
                        <h3 style="margin: 0;">📋 Problem-Details</h3>
                    </div>
                    <div style="padding: 20px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #059669; width: 120px;">🏗️ Anlage:</td>
                                <td style="padding: 8px 0;">{problem.bohrturm}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #059669;">🏢 Abteilung:</td>
                                <td style="padding: 8px 0;">{problem.abteilung}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #059669;">⚙️ System:</td>
                                <td style="padding: 8px 0;">{problem.system}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-weight: bold; color: #059669;">👤 Bearbeitet von:</td>
                                <td style="padding: 8px 0;">{problem.verantwortlicher or 'Nicht zugewiesen'}</td>
                            </tr>
                        </table>
                        <hr style="margin: 15px 0; border: none; border-top: 1px solid #dee2e6;">
                        <div>
                            <p style="font-weight: bold; color: #059669; margin-bottom: 10px;">⚠️ Ursprüngliches Problem:</p>
                            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin-bottom: 15px;">
                                {problem.problem}
                            </div>
                            
                            {f'<p style="font-weight: bold; color: #059669; margin-bottom: 10px;">🔧 Durchgeführte Maßnahmen:</p><div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 5px; padding: 15px; margin-bottom: 15px;">{problem.massnahmen}</div>' if problem.massnahmen else ''}
                            
                            <p style="font-weight: bold; color: #059669; margin-bottom: 10px;">📝 Abschlusskommentar:</p>
                            <div style="background: #e0f2fe; border: 1px solid #81d4fa; border-radius: 5px; padding: 15px;">
                                {kommentar if kommentar else 'Kein Kommentar hinterlassen'}
                            </div>
                            
                            {f'<p style="font-weight: bold; color: #059669; margin-bottom: 10px; margin-top: 15px;">📸 Dokumentation:</p><div style="background: #fef3c7; border: 1px solid #fbbf24; border-radius: 5px; padding: 15px;"><i class="bi bi-camera"></i> {len(problem.image_list)} Bild(er) verfügbar - In der App anzeigen für Details</div>' if problem.image_list else ''}
                        </div>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://192.168.188.20:5000/problem" 
                       style="background: #059669; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                        🔗 Neues Problem melden
                    </a>
                </div>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; font-size: 12px; color: #6c757d;">
                    <p style="margin: 0;">Diese E-Mail wurde automatisch von der Wartungs-App gesendet.</p>
                    <p style="margin: 5px 0 0 0;">Bitte nicht auf diese E-Mail antworten.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Text-Version als Fallback
        text_body = f"""
Problem abgearbeitet: {problem.bohrturm} - {problem.system}

Hallo {admin.username},

Ein Problem wurde als abgearbeitet markiert und wartet auf Ihre Prüfung:

Anlage: {problem.bohrturm}
Abteilung: {problem.abteilung}
System: {problem.system}
Bearbeitet von: {problem.verantwortlicher or 'Nicht zugewiesen'}

Ursprüngliches Problem:
{problem.problem}

{f'Durchgeführte Maßnahmen:\n{problem.massnahmen}\n' if problem.massnahmen else ''}
Abschlusskommentar:
{kommentar if kommentar else 'Kein Kommentar hinterlassen'}

Bitte loggen Sie sich in die Wartungs-App ein, um ein neues Problem zu melden:
http://192.168.188.20:5000/problem

Diese E-Mail wurde automatisch gesendet.
        """
        
        # Für Tests: E-Mails immer an nils.wanning@gmail.com senden
        test_recipient = "nils.wanning@gmail.com"
        
        # 🤖 EMAIL-BOT: Lokale Email-Speicherung (kein Google Mail)
        return save_email_locally(
            recipient=admin.email,
            recipient_name=admin.username,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            email_type="problem_completion",
            problem_id=problem.id
        )
        
    except Exception as e:
        logging.error(f"Fehler beim Senden der Problem-Abschluss-E-Mail: {e}")
        return False

# Routes
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        
        # Rate-Limiting: Maximal 5 Versuche pro IP in 15 Minuten
        current_time = datetime.now(timezone.utc)
        if client_ip in login_attempts:
            attempts = login_attempts[client_ip]
            # Alte Versuche entfernen (älter als 15 Minuten)
            attempts = [attempt for attempt in attempts if current_time - attempt < timedelta(minutes=15)]
            login_attempts[client_ip] = attempts
            
            if len(attempts) >= 5:
                logging.warning(f"Login rate limit exceeded for IP: {client_ip}")
                flash('Zu viele Login-Versuche. Bitte warten Sie 15 Minuten.', 'error')
                return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user'] = username
            # Erfolgreicher Login - Versuche zurücksetzen
            if client_ip in login_attempts:
                del login_attempts[client_ip]
            logging.info(f"Successful login for user: {username} from IP: {client_ip}")
            return redirect(url_for('problems'))
        else:
            # Fehlgeschlagener Login-Versuch protokollieren
            if client_ip not in login_attempts:
                login_attempts[client_ip] = []
            login_attempts[client_ip].append(current_time)
            logging.warning(f"Failed login attempt for user: {username} from IP: {client_ip}")
            flash('Ungültige Anmeldedaten', 'error')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session.get('user')).first()
    is_admin = user and user.username in ['nils', 'Admin']
    
    # Dashboard-Statistiken sammeln - nur aktive Probleme
    active_problems_query = Problem.query.filter(~Problem.status.in_(['abgearbeitet', 'bestätigt']))
    total_problems = active_problems_query.count()
    gemeldet_count = Problem.query.filter_by(status='gemeldet').count()
    in_bearbeitung_count = Problem.query.filter_by(status='in_bearbeitung').count()
    # Zeige Anzahl abgearbeiteter Probleme in Historie
    abgearbeitet_count = Problem.query.filter(Problem.status.in_(['abgearbeitet', 'bestätigt'])).count()
    
    # Probleme nach Abteilungen - nur aktive
    abteilungen = db.session.query(
        Problem.abteilung, 
        db.func.count(Problem.id).label('count')
    ).filter(~Problem.status.in_(['abgearbeitet', 'bestätigt'])).group_by(Problem.abteilung).all()
    
    # Probleme nach Bohrtürmen - nur aktive
    bohrtuerme = db.session.query(
        Problem.bohrturm, 
        db.func.count(Problem.id).label('count')
    ).filter(~Problem.status.in_(['abgearbeitet', 'bestätigt'])).group_by(Problem.bohrturm).all()
    
    # Letzte 5 aktive Probleme
    recent_problems = Problem.query.filter(~Problem.status.in_(['abgearbeitet', 'bestätigt'])).order_by(Problem.id.desc()).limit(5).all()
    
    # Kritische Probleme (gemeldet > 24h)
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    critical_problems = Problem.query.filter(
        Problem.status == 'gemeldet',
        Problem.status_changed_at < yesterday
    ).count()
    
    # Aktive Probleme mit Bildern
    problems_with_images = Problem.query.filter(
        Problem.images.isnot(None),
        ~Problem.status.in_(['abgearbeitet', 'bestätigt'])
    ).count()
    
    dashboard_data = {
        'total_problems': total_problems,
        'gemeldet_count': gemeldet_count,
        'in_bearbeitung_count': in_bearbeitung_count,
        'abgearbeitet_count': abgearbeitet_count,
        'abteilungen': abteilungen,
        'bohrtuerme': bohrtuerme,
        'recent_problems': recent_problems,
        'critical_problems': critical_problems,
        'problems_with_images': problems_with_images,
        'is_admin': is_admin
    }
    
    return render_template('dashboard.html', **dashboard_data)

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Sie wurden erfolgreich ausgeloggt.', 'success')
    return redirect(url_for('login'))

@app.route('/problem', methods=['GET', 'POST'])
def problem():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    current_user = session.get('user')
    user_facility = get_user_facility(current_user)
    is_admin = current_user in ['nils', 'Admin']
    
    # Alle Benutzer außer Admin für das Dropdown abrufen
    all_users = User.query.filter(User.username.notin_(['Admin', 'admin', 'ADMIN'])).all()
    
    if request.method == 'POST':
        # Sicherheitsprüfung: Facility-User darf nur für seine Anlage melden
        selected_facility = request.form['bohrturm']
        if not is_admin and user_facility and user_facility != selected_facility:
            flash(f'Fehler: Sie können nur Probleme für {user_facility} melden!', 'error')
            return render_template('problem.html', all_users=all_users, user_facility=user_facility, is_admin=is_admin)
        
        # Verarbeite Datei-Uploads
        uploaded_files = []
        if 'problem_images' in request.files:
            files = request.files.getlist('problem_images')
            uploaded_files = save_uploaded_files(files)
            if uploaded_files:
                flash(f'{len(uploaded_files)} Bild(er) erfolgreich hochgeladen.', 'success')
        
        # Erstelle neues Problem
        new_problem = Problem(
            bohrturm=request.form['bohrturm'],
            abteilung=request.form['abteilung'],
            system=request.form['system'],
            problem=request.form['problem']
        )
        
        # Automatische Zuweisung des Verantwortlichen basierend auf Anlage und Abteilung
        assigned_user = get_responsible_user(
            request.form['bohrturm'], 
            request.form['abteilung']
        )
        
        if assigned_user:
            new_problem.assigned_to = assigned_user.id
            new_problem.verantwortlicher = assigned_user.username
        
        # Setze Bildliste wenn Bilder vorhanden
        if uploaded_files:
            new_problem.image_list = uploaded_files
        
        db.session.add(new_problem)
        db.session.commit()
        
        # E-Mail-Benachrichtigung senden, wenn ein Benutzer zugewiesen wurde
        if assigned_user:
            if assigned_user.email:
                try:
                    # Prüfe E-Mail-Konfiguration
                    if not app.config.get('MAIL_PASSWORD'):
                        flash(f'Problem erfolgreich gemeldet! Automatisch zugewiesen an {assigned_user.username}. E-Mail-Versand nicht möglich: MAIL_PASSWORD nicht gesetzt.', 'warning')
                    else:
                        send_problem_assignment_email(assigned_user, new_problem)
                        flash(f'Problem erfolgreich gemeldet und automatisch an {assigned_user.username} zugewiesen! E-Mail gesendet.', 'success')
                except Exception as e:
                    logging.error(f'E-Mail-Versand fehlgeschlagen: {str(e)}')
                    flash(f'Problem erfolgreich gemeldet und an {assigned_user.username} zugewiesen, aber E-Mail-Versand fehlgeschlagen: {str(e)}', 'warning')
            else:
                flash(f'Problem erfolgreich gemeldet und automatisch an {assigned_user.username} zugewiesen! (Keine E-Mail-Adresse hinterlegt)', 'success')
        else:
            flash('Problem erfolgreich gemeldet! (Kein passender Verantwortlicher gefunden - bitte manuell zuweisen)', 'warning')
        
        return redirect(url_for('problems'))
    
    return render_template('problem.html', all_users=all_users, user_facility=user_facility, is_admin=is_admin)

@app.route('/problems')
def problems():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session.get('user')).first()
    is_admin = user and user.username in ['nils', 'Admin']
    current_user = session.get('user')
    user_facility = get_user_facility(current_user)
    
    # Suchparameter - zeige nur aktive Probleme (nicht abgearbeitet oder bestätigt)
    query = Problem.query.filter(~Problem.status.in_(['abgearbeitet', 'bestätigt']))
    
    # SICHERHEIT: Facility-User sehen alle Probleme zur Information, 
    # aber können nur ihre eigenen bearbeiten (wird in templates/edit_problem geprüft)
    # Keine Einschränkung der Anzeige, da sie alle Probleme zur Information sehen sollen
    
    bohrturm = request.args.get('bohrturm')
    abteilung = request.args.get('abteilung')
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    if bohrturm:
        query = query.filter(Problem.bohrturm == bohrturm)
    if abteilung:
        query = query.filter(Problem.abteilung == abteilung)
    if status:
        query = query.filter(Problem.status == status)
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Problem.status_changed_at >= date_from)
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d')
        date_to = date_to.replace(hour=23, minute=59, second=59)
        query = query.filter(Problem.status_changed_at <= date_to)

    # Performance-Optimierung: Mit Index und Eager Loading
    all_problems = query.order_by(
        case(
            (Problem.status == 'gemeldet', 1),
            (Problem.status == 'in_bearbeitung', 2),
            (Problem.status == 'abgearbeitet', 3),
        ),
        Problem.id.desc()
    ).limit(1000).all()  # Limit für bessere Performance bei großen Datenmengen
    
    # Alle User für Material-Besteller Dropdown
    all_users = User.query.all()
    
    # Template-Helper-Funktion für RSC-Check
    def is_rsc_for_problem(problem):
        if current_user in ['nils', 'Admin']:
            return True
        rsc_user = get_rsc_for_facility(problem.bohrturm)
        return rsc_user and rsc_user.username == current_user
    
    return render_template('problems.html', problems=all_problems, is_admin=is_admin, users=all_users, 
                         user_facility=user_facility, current_user=current_user,
                         is_rsc_for_problem=is_rsc_for_problem)

@app.route('/delete_problem/<int:problem_id>', methods=['GET', 'POST'])
def delete_problem(problem_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    problem = Problem.query.get_or_404(problem_id)
    user = User.query.filter_by(username=session.get('user')).first()
    is_admin = user and user.username in ['nils', 'Admin']
    current_user = session.get('user')
    
    # Sicherheitsprüfung: Nur Admins oder Benutzer der gleichen Anlage dürfen fertigstellen
    if not can_edit_facility(current_user, problem.bohrturm):
        flash(f'Fehler: Sie dürfen nur Probleme Ihrer eigenen Anlage fertigstellen!', 'error')
        return redirect(url_for('problems'))
    
    if request.method == 'POST':
        kommentar = request.form.get('kommentar', '')
        if is_admin and problem.status == 'abgearbeitet':
            # Admin bestätigt die Problemlösung - Problem bleibt in Historie
            # Statt löschen: Status auf "bestätigt" setzen oder anderweitig markieren
            problem.status = 'bestätigt'  # Neuer Status für bestätigte Probleme
            problem.loeschen_kommentar = kommentar + " [Admin bestätigt]"
            problem.status_changed_at = datetime.now(timezone.utc)
            db.session.commit()
            flash('Problem wurde bestätigt und bleibt in der Historie verfügbar.', 'success')
            return redirect(url_for('problems'))
        else:
            # Verarbeite Fertigstellungsbilder
            completion_images = []
            if 'completion_images' in request.files:
                files = request.files.getlist('completion_images')
                completion_images = save_uploaded_files(files)
                if completion_images:
                    flash(f'{len(completion_images)} Fertigstellungsbild(er) erfolgreich hochgeladen.', 'success')
            
            problem.status = 'abgearbeitet'
            problem.loeschen_kommentar = kommentar
            problem.status_changed_at = datetime.now()
            
            # Füge Fertigstellungsbilder zu den bestehenden Bildern hinzu
            if completion_images:
                existing_images = problem.image_list or []
                all_images = existing_images + completion_images
                problem.image_list = all_images
            
            db.session.commit()
            
            # E-Mail an Admin mit professionellem Design
            try:
                admin = User.query.filter(User.username.in_(['nils', 'Admin'])).first()
                if admin and admin.email:
                    send_problem_completion_email(admin, problem, kommentar)
            except Exception as e:
                flash(f'E-Mail konnte nicht gesendet werden: {str(e)}', 'error')
            
            flash('Problem wurde als abgearbeitet markiert.', 'success')
            return redirect(url_for('problems'))
    
    return render_template('delete_problem.html', problem=problem, is_admin=is_admin)

@app.route('/edit_problem/<int:problem_id>', methods=['GET', 'POST'])
def edit_problem(problem_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    problem = Problem.query.get_or_404(problem_id)
    current_user = session.get('user')
    
    # Sicherheitsprüfung: Nur Admins oder Benutzer der gleichen Anlage dürfen bearbeiten
    if not can_edit_facility(current_user, problem.bohrturm):
        flash(f'Fehler: Sie dürfen nur Probleme Ihrer eigenen Anlage bearbeiten!', 'error')
        return redirect(url_for('problems'))
    
    if request.method == 'POST':
        # Problem wird vom aktuell eingeloggten Benutzer übernommen (wie ursprünglich)
        current_user = session.get('user')
        problem.verantwortlicher = current_user
        
        # assigned_to auf aktuellen User setzen
        current_user_obj = User.query.filter_by(username=current_user).first()
        if current_user_obj:
            problem.assigned_to = current_user_obj.id
            
        problem.status = 'in_bearbeitung'
        problem.massnahmen = request.form.get('massnahmen', '')
        

            
        problem.status_changed_at = datetime.now(timezone.utc)
        db.session.commit()
        
        # Interested Parties benachrichtigen
        interested_parties = request.form.getlist('interested_parties')
        notification_count = 0
        
        for username in interested_parties:
            if username and username != current_user:  # Nicht sich selbst benachrichtigen
                try:
                    interested_user = User.query.filter_by(username=username).first()
                    if interested_user and interested_user.email:
                        send_problem_notification_email(interested_user, problem, current_user)
                        notification_count += 1
                except Exception as e:
                    print(f"E-Mail an {username} konnte nicht gesendet werden: {str(e)}")
        
        # Erfolgs-Meldung anzeigen
        if notification_count > 0:
            flash(f'Problem wurde übernommen und {notification_count} Beteiligte wurden per E-Mail informiert.', 'success')
        else:
            flash('Problem wurde erfolgreich übernommen.', 'success')
            
        return redirect(url_for('problems'))
    
    # Nur User der gleichen Anlage für Dropdown laden
    facility = problem.bohrturm  # z.B. "T-207"
    facility_prefix = facility.replace('-', '')  # z.B. "T207"
    
    # Filtere User: Admins + User der gleichen Anlage
    users = User.query.filter(
        db.or_(
            User.username.in_(['nils', 'Admin']),  # Admins
            User.username.like(f'{facility_prefix}%')  # z.B. T207 EL, T207 MECH, etc.
        )
    ).all()
    
    return render_template('edit_problem.html', problem=problem, users=users)

@app.route('/confirm_order/<int:problem_id>', methods=['GET', 'POST'])
def confirm_order(problem_id):
    """Bestellbestätigung - nur für den ausgewählten Besteller zugänglich"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    problem = Problem.query.get_or_404(problem_id)
    
    # Prüfung: Nur der ausgewählte Besteller darf diese Route verwenden
    if not problem.besteller_id:
        flash('Diesem Problem ist kein Besteller zugewiesen.', 'error')
        return redirect(url_for('problems'))
    
    # Aktueller Benutzer muss der Besteller sein
    current_user = User.query.filter_by(username=session['user']).first()
    if not current_user or current_user.id != problem.besteller_id:
        flash('Sie sind nicht berechtigt, diese Bestellung zu bestätigen.', 'error')
        return redirect(url_for('problems'))
    
    # Prüfung: Problem muss Material-Bestellung erfordern
    if not problem.bestellung_benoetigt:
        flash('Für dieses Problem ist keine Material-Bestellung erforderlich.', 'error')
        return redirect(url_for('problems'))
    
    # Prüfung: Bestellung bereits bestätigt
    if problem.bestellung_bestaetigt:
        flash('Diese Bestellung wurde bereits bestätigt.', 'info')
    
    if request.method == 'POST':
        # Bestellbestätigung verarbeiten
        problem.bestellung_bestaetigt = True
        problem.pr_nummer = request.form.get('pr_nummer', '').strip()
        
        # Lieferdatum verarbeiten
        lieferdatum_str = request.form.get('lieferdatum', '').strip()
        if lieferdatum_str:
            try:
                problem.lieferdatum = datetime.strptime(lieferdatum_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Ungültiges Datumsformat. Bitte verwenden Sie das Format YYYY-MM-DD.', 'error')
                return render_template('confirm_order.html', problem=problem)
        
        problem.bestellung_bestaetigt_am = datetime.now(timezone.utc)
        
        db.session.commit()
        
        flash('Bestellung wurde erfolgreich bestätigt!', 'success')
        logging.info(f"Material-Bestellung bestätigt für Problem #{problem.id} von {current_user.username}")
        
        return redirect(url_for('problems'))
    
    return render_template('confirm_order.html', problem=problem)

@app.route('/add_progress_update/<int:problem_id>', methods=['POST'])
def add_progress_update(problem_id):
    """Fügt ein Fortschritt-Update zu einem Problem hinzu"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    problem = Problem.query.get_or_404(problem_id)
    current_user = session.get('user')
    
    # Sicherheitsprüfung: Nur Admins oder Benutzer der gleichen Anlage dürfen Updates hinzufügen
    if not can_edit_facility(current_user, problem.bohrturm):
        flash(f'Fehler: Sie dürfen nur Updates für Probleme Ihrer eigenen Anlage hinzufügen!', 'error')
        return redirect(url_for('problems'))
    
    # Nur bei Problemen in Bearbeitung
    if problem.status != 'in_bearbeitung':
        flash('Updates können nur bei Problemen in Bearbeitung hinzugefügt werden.', 'error')
        return redirect(url_for('problems'))
    
    update_text = request.form.get('update_text', '').strip()
    if not update_text:
        flash('Bitte geben Sie einen Update-Text ein.', 'error')
        return redirect(url_for('problems'))
    
    # Aktuellen User holen
    current_user = session.get('user')
    
    # Neues Update erstellen
    new_update = {
        'text': update_text,
        'user': current_user,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    # Aktuelle Updates laden oder neue Liste erstellen
    current_updates = problem.progress_update_list
    current_updates.append(new_update)
    
    # Updates speichern
    problem.progress_update_list = current_updates
    problem.status_changed_at = datetime.now(timezone.utc)
    
    db.session.commit()

    flash(f'Fortschritt-Update hinzugefügt: "{update_text}"', 'success')
    return redirect(url_for('problems') + f'#detailModal{problem_id}')

@app.route('/add_material/<int:problem_id>', methods=['POST'])
def add_material(problem_id):
    """Fügt ein Material-Item zu einem Problem hinzu"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    problem = Problem.query.get_or_404(problem_id)
    current_user = session.get('user')
    
    # Sicherheitsprüfung: Nur Admins oder Benutzer der gleichen Anlage dürfen Material hinzufügen
    if not can_edit_facility(current_user, problem.bohrturm):
        flash(f'Fehler: Sie dürfen nur Material für Probleme Ihrer eigenen Anlage hinzufügen!', 'error')
        return redirect(url_for('problems'))
    
    mm_nummer = request.form.get('mm_nummer', '').strip()
    beschreibung = request.form.get('beschreibung', '').strip()
    menge = int(request.form.get('menge', 1) or 1)
    einheit = request.form.get('einheit', 'Stück').strip()
    
    if not mm_nummer or not beschreibung:
        flash('MM-Nummer und Beschreibung sind erforderlich.', 'error')
        return redirect(url_for('problems'))
    
    # Aktuell eingeloggten Benutzer als Besteller verwenden
    current_user_obj = User.query.filter_by(username=current_user).first()
    besteller_id = current_user_obj.id if current_user_obj else None
    
    # Neues Material-Item erstellen
    material_item = MaterialItem(
        problem_id=problem_id,
        mm_nummer=mm_nummer,
        beschreibung=beschreibung,
        menge=menge,
        einheit=einheit,
        besteller_id=besteller_id
    )
    
    db.session.add(material_item)
    db.session.commit()
    
    # 📧 RSC-BENACHRICHTIGUNG: Material wurde angefordert
    try:
        print(f"🔍 DEBUG: Suche RSC für Anlage: {problem.bohrturm}")
        rsc_user = get_rsc_for_facility(problem.bohrturm)
        print(f"🔍 DEBUG: RSC gefunden: {rsc_user.username if rsc_user else 'None'}")
        
        if rsc_user:
            print(f"🔍 DEBUG: Sende E-Mail an RSC: {rsc_user.username} ({rsc_user.email})")
            success = send_material_request_email(
                rsc_user=rsc_user,
                problem=problem,
                material_item=material_item,
                requester_name=current_user
            )
            print(f"🔍 DEBUG: E-Mail-Versand erfolgreich: {success}")
            
            if success:
                flash(f'Material "{beschreibung}" hinzugefügt. 📧 RSC {rsc_user.username} wurde benachrichtigt.', 'success')
            else:
                flash(f'Material "{beschreibung}" hinzugefügt. ⚠️ RSC-Benachrichtigung fehlgeschlagen.', 'warning')
        else:
            print(f"🔍 DEBUG: Kein RSC für {problem.bohrturm} gefunden!")
            flash(f'Material "{beschreibung}" hinzugefügt. ⚠️ Kein RSC für {problem.bohrturm} gefunden.', 'warning')
    except Exception as e:
        print(f"🔍 DEBUG: Fehler bei RSC-Benachrichtigung: {str(e)}")
        logging.error(f"Fehler bei RSC-Benachrichtigung: {str(e)}")
        flash(f'Material "{beschreibung}" hinzugefügt. ⚠️ RSC-Benachrichtigung fehlgeschlagen.', 'warning')
    
    return redirect(url_for('problems') + f'#detailModal{problem_id}-material')

@app.route('/confirm_material/<int:material_id>', methods=['POST'])
def confirm_material(material_id):
    """Bestätigt eine Material-Bestellung (nur für RSCs und Admins)"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    material = MaterialItem.query.get_or_404(material_id)
    current_user = session.get('user')
    facility = material.problem.bohrturm
    
    # NEUE RSC-BERECHTIGUNG: Nur RSCs der Anlage und Admins dürfen Material-Bestellungen verwalten
    if not can_manage_material_orders(current_user, facility):
        flash(f'Fehler: Nur der RSC der Anlage {facility} oder Admins dürfen Material-Bestellungen verwalten!', 'error')
        return redirect(url_for('problems'))
    
    # Material-Bestellung mit PR, PO und Lieferdatum verarbeiten
    material.bestellt = True
    material.bestellt_am = datetime.now(timezone.utc)
    material.pr_nummer = request.form.get('pr_nummer', '').strip()
    material.po_nummer = request.form.get('po_nummer', '').strip()
    
    # Lieferdatum verarbeiten
    lieferdatum_str = request.form.get('lieferdatum', '').strip()
    if lieferdatum_str:
        try:
            material.lieferdatum = datetime.strptime(lieferdatum_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Ungültiges Lieferdatum-Format. Bitte verwenden Sie YYYY-MM-DD.', 'warning')
    
    db.session.commit()
    
    flash(f'Material-Bestellung "{material.beschreibung}" wurde von RSC bestätigt.', 'success')
    return redirect(url_for('problems') + f'#detailModal{material.problem_id}-material')

@app.route('/update_material_field/<int:material_id>', methods=['POST'])
def update_material_field(material_id):
    """Aktualisiert ein Feld eines MaterialItems (nur für RSCs)"""
    if 'user' not in session:
        return {'success': False, 'error': 'Nicht eingeloggt'}, 401
    
    material = MaterialItem.query.get_or_404(material_id)
    current_user = session.get('user')
    
    # Prüfen ob der User berechtigt ist (RSC der Anlage oder Admin)
    if not can_manage_material_orders(current_user, material.problem.bohrturm):
        return {'success': False, 'error': 'Keine Berechtigung für Material-Order-Management'}, 403
    
    try:
        data = request.get_json()
        field = data.get('field')
        value = data.get('value')
        
        if field == 'pr_nummer':
            material.pr_nummer = value if value else None
        elif field == 'po_nummer':
            material.po_nummer = value if value else None
        elif field == 'lieferdatum':
            if value:
                material.lieferdatum = datetime.strptime(value, '%Y-%m-%d').date()
            else:
                material.lieferdatum = None
        else:
            return {'success': False, 'error': 'Ungültiges Feld'}, 400
        
        db.session.commit()
        return {'success': True}
        
    except ValueError as e:
        return {'success': False, 'error': f'Ungültiges Datum-Format: {str(e)}'}, 400
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': f'Fehler: {str(e)}'}, 500

@app.route('/delete_material/<int:material_id>', methods=['DELETE'])
def delete_material(material_id):
    """Löscht ein Material-Item mit Force-Option"""
    print(f"🗑️ DEBUG delete_material: material_id={material_id}")
    
    if 'user' not in session:
        print("❌ DEBUG: Benutzer nicht eingeloggt")
        return {'success': False, 'error': 'Nicht eingeloggt'}, 401
    
    material = MaterialItem.query.get_or_404(material_id)
    current_user = session.get('user')
    
    print(f"🗑️ DEBUG: current_user={current_user}, material.problem.bohrturm={material.problem.bohrturm}")
    
    # Sicherheitsprüfung: Nur Admins oder Benutzer der gleichen Anlage
    if not can_edit_facility(current_user, material.problem.bohrturm):
        print("❌ DEBUG: Keine Berechtigung zum Löschen")
        return {'success': False, 'error': 'Sie dürfen nur Material für Probleme Ihrer eigenen Anlage löschen!'}, 403
    
    user = User.query.filter_by(username=session['user']).first()
    if not user:
        print("❌ DEBUG: Benutzer nicht gefunden")
        return {'success': False, 'error': 'Benutzer nicht gefunden'}, 403
    
    try:
        print(f"🗑️ DEBUG: Lösche Material-Item {material.id}: {material.beschreibung}")
        
        # Force-Delete: Erst alle Abhängigkeiten prüfen und entfernen
        material_beschreibung = material.beschreibung
        material_problem_id = material.problem_id
        
        # Lösche das Material-Item
        db.session.delete(material)
        db.session.commit()
        
        print(f"✅ DEBUG: Material-Item erfolgreich gelöscht: {material_beschreibung}")
        return {'success': True, 'message': f'Material "{material_beschreibung}" wurde gelöscht'}, 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ DEBUG: Fehler beim Löschen: {e}")
        
        # Force-Delete: Ignoriere Constraints und lösche direkt
        try:
            print("🔧 DEBUG: Versuche Force-Delete...")
            from sqlalchemy import text
            
            with db.engine.connect() as conn:
                # Direktes SQL-Delete ohne Constraint-Prüfung
                result = conn.execute(text("DELETE FROM material_item WHERE id = :material_id"), 
                                    {"material_id": material_id})
                conn.commit()
                
                if result.rowcount > 0:
                    print(f"✅ DEBUG: Force-Delete erfolgreich: {result.rowcount} Zeile(n) gelöscht")
                    return {'success': True, 'message': 'Material wurde force-gelöscht'}, 200
                else:
                    print("❌ DEBUG: Force-Delete fehlgeschlagen - keine Zeilen betroffen")
                    return {'success': False, 'error': 'Material nicht gefunden'}, 404
                    
        except Exception as force_error:
            print(f"❌ DEBUG: Force-Delete Fehler: {force_error}")
            return {'success': False, 'error': f'Löschen fehlgeschlagen: {str(force_error)}'}, 500

@app.route('/admin/delete_email/<filename>', methods=['DELETE'])
def admin_delete_email(filename):
    """🗑️ Email löschen - nur für Admins"""
    logging.info(f"=== EMAIL DELETE DEBUG === Filename: {filename}")
    
    if 'user' not in session:
        return {'success': False, 'error': 'Nicht eingeloggt'}, 401
    
    user = User.query.filter_by(username=session['user']).first()
    is_admin = user.username in ['nils', 'Admin'] if user else False
    
    if not user or not is_admin:
        return {'success': False, 'error': 'Keine Berechtigung'}, 403
    
    try:
        import os
        email_dir = os.path.join(os.path.dirname(__file__), 'logs', 'emails')
        
        # Sicherheitscheck: Nur erlaubte Dateitypen
        if not (filename.endswith('.json') or filename.endswith('.html')):
            return {'success': False, 'error': 'Ungültiger Dateityp'}, 400
        
        # Beide Dateien löschen (JSON und HTML)
        base_name = filename.replace('.json', '').replace('.html', '')
        json_file = os.path.join(email_dir, base_name + '.json')
        html_file = os.path.join(email_dir, base_name + '.html')
        
        deleted_files = []
        if os.path.exists(json_file):
            os.remove(json_file)
            deleted_files.append(base_name + '.json')
        if os.path.exists(html_file):
            os.remove(html_file)
            deleted_files.append(base_name + '.html')
        
        if deleted_files:
            logging.info(f"EMAIL-BOT: Emails gelöscht von {user.username}: {', '.join(deleted_files)}")
            return {'success': True, 'deleted_files': deleted_files}
        else:
            return {'success': False, 'error': 'Email nicht gefunden'}, 404
            
    except Exception as e:
        logging.error(f"Fehler beim Email-Löschen: {e}")
        return {'success': False, 'error': str(e)}, 500

@app.route('/admin_users', methods=['GET', 'POST'])
def admin_users():
    if 'user' not in session or session['user'] not in ['nils', 'Admin']:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Password reset
        user_id = request.form.get('reset_user_id')
        new_password = request.form.get('new_password')
        
        if user_id and new_password:
            user = User.query.get(user_id)
            if user:
                try:
                    user.password = generate_password_hash(new_password)
                    db.session.commit()
                    flash('Passwort wurde zurückgesetzt.', 'success')
                except Exception as e:
                    flash('Fehler beim Zurücksetzen des Passworts.', 'error')
                    db.session.rollback()
            else:
                flash('Benutzer nicht gefunden.', 'error')
        else:
            flash('Ungültige Daten.', 'error')
        
        return redirect(url_for('admin_users'))

        # Email update
        update_email_user_id = request.form.get('update_email_user_id')
        new_email = request.form.get('new_email')
        if update_email_user_id and new_email:
            import re
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", new_email):
                flash('Ungültige E-Mail-Adresse.', 'danger')
            elif User.query.filter(User.email == new_email, User.id != int(update_email_user_id)).first():
                flash('E-Mail-Adresse bereits vergeben.', 'danger')
            else:
                user2 = User.query.get(update_email_user_id)
                if user2:
                    user2.email = new_email
                    db.session.commit()
                    flash('E-Mail wurde aktualisiert.', 'success')
        
        return redirect(url_for('admin_users'))
        # Create new user
        if request.form.get('create_user'):
            new_username = request.form.get('new_username')
            new_email_addr = request.form.get('new_email')
            new_password = request.form.get('new_password')
            
            if not new_username or not new_email_addr or not new_password:
                flash('Alle Felder sind erforderlich.', 'danger')
            elif User.query.filter((User.username == new_username) | (User.email == new_email_addr)).first():
                flash('Benutzername oder E-Mail bereits vergeben.', 'danger')
            else:
                    # Create user with a temporary unusable password; require set via one-time token
                    temp_pw = generate_password_hash(os.urandom(16).hex())
                    user = User(username=new_username, email=new_email_addr, password=temp_pw)
                    db.session.add(user)
                    db.session.commit()
                    # generate secure token
                    import secrets
                    token = secrets.token_urlsafe(48)
                    ott = OneTimeToken(token=token, user_id=user.id)
                    db.session.add(ott)
                    db.session.commit()
                    # 🤖 EMAIL-BOT: Password-Setup Email lokal speichern
                    try:
                        set_url = url_for('set_password', token=token, _external=True)
                        
                        subject = 'Wartungs-App: Passwort setzen'
                        text_body = f"""Hallo {new_username},

Ein Administrator hat ein Konto für dich angelegt. Bitte setze dein persönliches Passwort über den folgenden Link:

{set_url}

Dieser Link ist einmalig und sollte aus Sicherheitsgründen zeitnah verwendet werden.

Bei Fragen: Nils Wanning

Viele Grüße
Wartungs-App Team
"""
                        
                        html_body = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                                <div style="background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                                    <h1 style="margin: 0; font-size: 24px;">🔐 Passwort setzen</h1>
                                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Wartungs-App Konto aktivieren</p>
                                </div>
                                
                                <div style="background: #dbeafe; padding: 20px; border-radius: 8px; border-left: 4px solid #3b82f6;">
                                    <h3 style="color: #1e40af; margin-top: 0;">Hallo {new_username},</h3>
                                    <p>Ein Administrator hat ein Konto für dich angelegt. Bitte setze dein persönliches Passwort über den folgenden Link:</p>
                                </div>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{set_url}" 
                                       style="background: #3b82f6; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                                        🔐 Passwort jetzt setzen
                                    </a>
                                </div>
                                
                                <div style="background: #fef3c7; padding: 15px; border-radius: 5px; text-align: center; font-size: 12px; color: #92400e;">
                                    <p style="margin: 0;">Dieser Link ist einmalig und sollte zeitnah verwendet werden.</p>
                                    <p style="margin: 5px 0 0 0;">Bei Fragen: Nils Wanning</p>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                        
                        # Speichere Email lokal
                        save_email_locally(
                            recipient=new_email_addr,
                            recipient_name=new_username,
                            subject=subject,
                            html_body=html_body,
                            text_body=text_body,
                            email_type="password_setup"
                        )
                        flash(f'Benutzer {new_username} erstellt. Setup-Link: {set_url}', 'success')
                            
                    except Exception as e:
                        set_url = url_for('set_password', token=token, _external=True)
                        flash(f'Benutzer erstellt, aber Email-Fehler. Setup-Link: {set_url}', 'warning')
        
        return redirect(url_for('admin_users'))
    
    users = User.query.all()
    return render_template('admin_users.html', users=users)


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    # Only allow admins
    if 'user' not in session or session['user'] not in ['nils', 'Admin']:
        return redirect(url_for('login'))

    # Protect core admin accounts from accidental deletion
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.username in ['nils', 'Admin']:
        flash('Dieser Benutzer kann nicht gelöscht werden.', 'danger')
        return redirect(url_for('admin_users'))

    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash('Benutzer wurde gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Löschen des Benutzers: {str(e)}', 'danger')

    return redirect(url_for('admin_users'))

@app.route('/admin_emails')
def admin_emails():
    """📧 Admin-Ansicht für Email-Bot - Zeigt alle lokal gespeicherten Emails"""
    logging.info("=== EMAIL-BOT ADMIN ACCESS DEBUG ===")
    logging.info(f"Session keys: {list(session.keys())}")
    logging.info(f"Session user: {session.get('user', 'NOT FOUND')}")
    
    if 'user' not in session:
        logging.warning("REDIRECT TO LOGIN: user not in session")
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session['user']).first()
    logging.info(f"User lookup result: {user}")
    if not user:
        logging.warning("REDIRECT TO LOGIN: user not found in database")
        return redirect(url_for('login'))
    
    is_admin = user.username in ['nils', 'Admin']
    logging.info(f"User found: {user.username}, is_admin: {is_admin}")
    
    # Nur Admins haben Zugriff - wie bei anderen Admin-Funktionen
    if not is_admin:
        logging.warning(f"REDIRECT TO PROBLEMS: user {user.username} is not admin")
        flash('Nur Administratoren haben Zugriff auf die Email-Verwaltung.', 'danger')
        return redirect(url_for('problems'))
    
    logging.info(f"SUCCESS: Admin {user.username} accessing email-bot interface")
    
    try:
        import os
        import json
        from datetime import datetime
        
        email_dir = os.path.join(os.path.dirname(__file__), 'logs', 'emails')
        emails = []
        
        if os.path.exists(email_dir):
            for filename in os.listdir(email_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(email_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            email_data = json.load(f)
                            email_data['filename'] = filename
                            emails.append(email_data)
                    except Exception as e:
                        logging.error(f"Fehler beim Laden der Email {filename}: {e}")
        
        # Sortiere Emails nach Timestamp (neueste zuerst)
        emails.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return render_template('admin_emails.html', emails=emails)
        
    except Exception as e:
        logging.error(f"Fehler in admin_emails: {e}")
        flash(f'Fehler beim Laden der Emails: {str(e)}', 'danger')
        return redirect(url_for('admin_users'))

@app.route('/admin/email_preview/<filename>')
def admin_email_preview(filename):
    """📧 Email-Vorschau im Browser"""
    logging.info(f"=== EMAIL PREVIEW DEBUG === Filename: {filename}")
    logging.info(f"Session user: {session.get('user', 'NOT FOUND')}")
    
    if 'user' not in session:
        logging.warning("EMAIL PREVIEW REDIRECT: user not in session")
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session['user']).first()
    is_admin = user.username in ['nils', 'Admin'] if user else False
    logging.info(f"Email preview user: {user}, is_admin: {is_admin}")
    
    if not user or not is_admin:
        logging.warning(f"EMAIL PREVIEW REDIRECT: user {user} or not admin")
        return redirect(url_for('login'))
    
    try:
        import os
        email_dir = os.path.join(os.path.dirname(__file__), 'logs', 'emails')
        
        # Sicherheitscheck: Nur .html Dateien
        if not filename.endswith('.html'):
            return "Ungültiger Dateityp", 400
        
        filepath = os.path.join(email_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return "Email nicht gefunden", 404
            
    except Exception as e:
        logging.error(f"Fehler beim Email-Preview: {e}")
        return f"Fehler: {str(e)}", 500


@app.route('/admin/delete_problem/<int:problem_id>', methods=['POST'])
def admin_delete_problem(problem_id):
    """Force-Delete für Probleme mit allen zugehörigen Material-Items"""
    # Nur Admins erlauben
    if 'user' not in session or session['user'] not in ['nils', 'Admin']:
        flash('Keine Berechtigung für diese Aktion.', 'danger')
        return redirect(url_for('problems'))
    
    problem = Problem.query.get_or_404(problem_id)
    print(f"🗑️ DEBUG admin_delete_problem: problem_id={problem_id}, problem='{problem.problem}'")
    
    try:
        # Lösche verknüpfte Bilddateien falls vorhanden
        if problem.image_list:
            import os
            for image_file in problem.image_list:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_file)
                if os.path.exists(image_path):
                    os.remove(image_path)
                    print(f"🗑️ DEBUG: Bild gelöscht: {image_file}")
        
        # FORCE-DELETE: Erst alle Material-Items löschen
        materials = MaterialItem.query.filter_by(problem_id=problem_id).all()
        print(f"🗑️ DEBUG: {len(materials)} Material-Items gefunden")
        
        for material in materials:
            print(f"🗑️ DEBUG: Lösche Material-Item {material.id}: {material.beschreibung}")
            db.session.delete(material)
        
        # Dann das Problem löschen
        print(f"🗑️ DEBUG: Lösche Problem {problem_id}")
        db.session.delete(problem)
        db.session.commit()
        
        print(f"✅ DEBUG: Problem #{problem_id} und alle Material-Items erfolgreich gelöscht")
        flash(f'Problem #{problem_id} wurde erfolgreich gelöscht.', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ DEBUG: Normales Löschen fehlgeschlagen: {e}")
        
        # FORCE-DELETE mit direktem SQL
        try:
            print("🔧 DEBUG: Versuche Force-Delete mit direktem SQL...")
            from sqlalchemy import text
            
            with db.engine.connect() as conn:
                # Erst Material-Items löschen
                result_materials = conn.execute(text("DELETE FROM material_item WHERE problem_id = :problem_id"), 
                                              {"problem_id": problem_id})
                print(f"🔧 DEBUG: {result_materials.rowcount} Material-Items force-gelöscht")
                
                # Dann Problem löschen
                result_problem = conn.execute(text("DELETE FROM problem WHERE id = :problem_id"), 
                                            {"problem_id": problem_id})
                print(f"🔧 DEBUG: {result_problem.rowcount} Problem force-gelöscht")
                
                conn.commit()
                
                if result_problem.rowcount > 0:
                    print(f"✅ DEBUG: Force-Delete erfolgreich!")
                    flash(f'Problem #{problem_id} wurde force-gelöscht.', 'success')
                else:
                    print("❌ DEBUG: Problem nicht gefunden")
                    flash('Problem nicht gefunden.', 'warning')
                    
        except Exception as force_error:
            print(f"❌ DEBUG: Force-Delete fehlgeschlagen: {force_error}")
            flash(f'Force-Delete fehlgeschlagen: {str(force_error)}', 'danger')
    
    return redirect(url_for('problems'))


@app.route('/set_password/<token>', methods=['GET', 'POST'])
def set_password(token):
    ott = OneTimeToken.query.filter_by(token=token, used=False).first()
    if not ott:
        flash('Ungültiger oder bereits verwendeter Link.', 'danger')
        return redirect(url_for('login'))

    # check expiry (e.g., 48 hours)
    if datetime.now(timezone.utc) - ott.created_at > timedelta(hours=48):
        flash('Der Link ist abgelaufen.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(ott.user_id)
    if request.method == 'POST':
        pw = request.form.get('password')
        pw2 = request.form.get('password2')
        if not pw or pw != pw2:
            flash('Passwörter stimmen nicht überein oder sind leer.', 'danger')
            return render_template('set_password.html', token=token)
        user.password = generate_password_hash(pw)
        ott.used = True
        db.session.commit()
        # Log the user in after setting password
        session['user'] = user.username
        flash('Passwort gesetzt. Du bist jetzt eingeloggt.', 'success')
        return redirect(url_for('problems'))

    return render_template('set_password.html', token=token)


@app.route('/history')
def history():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    username = session['user']
    user = User.query.filter_by(username=username).first()
    is_admin = user and user.username in ['nils', 'Admin']
    
    # Nur Admins können die komplette Historie sehen
    if not is_admin:
        flash('Keine Berechtigung für diese Seite.', 'error')
        return redirect(url_for('problems'))
    
    # Suchparameter für Historie - zeige sowohl abgearbeitete als auch bestätigte Probleme
    query = Problem.query.filter(Problem.status.in_(['abgearbeitet', 'bestätigt']))
    bohrturm = request.args.get('bohrturm')
    abteilung = request.args.get('abteilung') 
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search_term = request.args.get('search')

    if bohrturm:
        query = query.filter(Problem.bohrturm == bohrturm)
    if abteilung:
        query = query.filter(Problem.abteilung == abteilung)
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Problem.status_changed_at >= date_from)
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d')
        date_to = date_to.replace(hour=23, minute=59, second=59)
        query = query.filter(Problem.status_changed_at <= date_to)
    if search_term:
        query = query.filter(
            Problem.problem.contains(search_term) |
            Problem.loeschen_kommentar.contains(search_term) |
            Problem.massnahmen.contains(search_term)
        )

    # Sortierung: Neueste zuerst
    archived_problems = query.order_by(Problem.status_changed_at.desc()).all()
    
    # Statistiken für die Historie
    total_archived = len(archived_problems)
    problems_with_images = len([p for p in archived_problems if p.image_list])
    
    # Eindeutige Werte für Filter-Dropdowns
    all_bohrtuerme = db.session.query(Problem.bohrturm).filter_by(status='abgearbeitet').distinct().all()
    all_abteilungen = db.session.query(Problem.abteilung).filter_by(status='abgearbeitet').distinct().all()
    
    return render_template('history.html', 
                         problems=archived_problems,
                         total_archived=total_archived,
                         problems_with_images=problems_with_images,
                         bohrtuerme=[b[0] for b in all_bohrtuerme],
                         abteilungen=[a[0] for a in all_abteilungen],
                         is_admin=is_admin)

@app.route('/history/delete/<int:problem_id>', methods=['POST'])
def delete_from_history(problem_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session.get('user')).first()
    is_admin = user and user.username in ['nils', 'Admin']
    
    if not is_admin:
        flash('Keine Berechtigung für diese Aktion.', 'error')
        return redirect(url_for('history'))
    
    problem = Problem.query.get_or_404(problem_id)
    
    # Nur abgearbeitete/bestätigte Probleme können aus der Historie gelöscht werden
    if problem.status not in ['abgearbeitet', 'bestätigt']:
        flash('Nur abgearbeitete/bestätigte Probleme können aus der Historie gelöscht werden.', 'error')
        return redirect(url_for('history'))
    
    try:
        # Lösche zuerst alle verknüpften MaterialItem-Einträge
        material_items = MaterialItem.query.filter_by(problem_id=problem_id).all()
        for material_item in material_items:
            db.session.delete(material_item)
        
        # Lösche verknüpfte Bilddateien falls vorhanden
        if problem.image_list:
            for image_file in problem.image_list:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_file)
                if os.path.exists(image_path):
                    os.remove(image_path)
        
        # Lösche das Problem aus der Datenbank
        db.session.delete(problem)
        db.session.commit()
        flash(f'Problem #{problem_id} wurde erfolgreich aus der Historie gelöscht.', 'success')
        logging.info(f"Problem #{problem_id} aus Historie gelöscht von {session.get('user')}")
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Löschen des Problems: {str(e)}', 'error')
        logging.error(f"Fehler beim Löschen von Problem #{problem_id}: {e}")
    
    return redirect(url_for('history'))

@app.route('/history/bulk-delete', methods=['POST'])
def bulk_delete_from_history():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session.get('user')).first()
    is_admin = user and user.username in ['nils', 'Admin']
    
    if not is_admin:
        flash('Keine Berechtigung für diese Aktion.', 'error')
        return redirect(url_for('history'))
    
    selected_ids = request.form.getlist('selected_problems')
    if not selected_ids:
        flash('Keine Probleme ausgewählt.', 'warning')
        return redirect(url_for('history'))
    
    deleted_count = 0
    errors = []
    
    for problem_id in selected_ids:
        try:
            problem = Problem.query.get(int(problem_id))
            if problem and problem.status in ['abgearbeitet', 'bestätigt']:
                # Lösche zuerst alle verknüpften MaterialItem-Einträge
                material_items = MaterialItem.query.filter_by(problem_id=int(problem_id)).all()
                for material_item in material_items:
                    db.session.delete(material_item)
                
                # Lösche verknüpfte Bilddateien
                if problem.image_list:
                    for image_file in problem.image_list:
                        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_file)
                        if os.path.exists(image_path):
                            os.remove(image_path)
                
                db.session.delete(problem)
                deleted_count += 1
        except Exception as e:
            errors.append(f"Problem #{problem_id}: {str(e)}")
    
    try:
        db.session.commit()
        flash(f'{deleted_count} Problem(e) erfolgreich aus der Historie gelöscht.', 'success')
        logging.info(f"{deleted_count} Probleme aus Historie gelöscht von {session.get('user')}")
        
        if errors:
            for error in errors:
                flash(f'Fehler: {error}', 'warning')
                
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Bulk-Löschen: {str(e)}', 'error')
        logging.error(f"Bulk-Delete-Fehler: {e}")
    
    return redirect(url_for('history'))

# Error Handlers für bessere Benutzererfahrung
@app.errorhandler(404)
def not_found_error(error):
    logging.warning(f"404 Error: {request.url}")
    return render_template('base.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logging.error(f"500 Error: {error}")
    return render_template('base.html'), 500


@app.errorhandler(413)
def file_too_large(error):
    flash('Die hochgeladene Datei ist zu groß. Maximum: 16MB', 'error')
    return redirect(request.url)


# Sicherheits-Headers für bessere Sicherheit
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Für HTTPS (wenn verfügbar)
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


# === ADMIN SERVER MANAGEMENT ===
@app.route('/admin/restart_server', methods=['POST'])
def admin_restart_server():
    """🔧 Admin Route für Server-Neustart"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401
    
    username = session['user']
    if username not in ['nils', 'Admin']:
        return jsonify({'success': False, 'message': 'Keine Admin-Berechtigung'}), 403

    # Neustart in einem Thread starten
    import threading
    import time
    import os
    import sys
    
    def restart_server():
        time.sleep(1)  # Kurz warten, damit die Response gesendet wird
        try:
            # Server-Prozess beenden und neu starten
            os.system('taskkill /f /im python.exe & timeout 2 & python app.py')
        except Exception as e:
            logging.error(f'Fehler beim Server-Neustart: {e}')
    
    restart_thread = threading.Thread(target=restart_server)
    restart_thread.daemon = True
    restart_thread.start()
    
    return jsonify({'success': True, 'message': 'Server wird neu gestartet...'})


# ===== MATERIAL-MANAGEMENT ROUTES =====
@app.route('/api/material_search')
def material_search():
    """AJAX-API für Material-Suche im Katalog"""
    if 'user' not in session:
        return jsonify({'error': 'Nicht eingeloggt'}), 401
    
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'results': []})
    
    # Suche im Material-Katalog
    materials = MaterialCatalog.query.filter(
        db.or_(
            MaterialCatalog.mm_nummer.contains(query),
            MaterialCatalog.beschreibung.contains(query)
        )
    ).limit(10).all()
    
    results = []
    for material in materials:
        results.append({
            'mm_nummer': material.mm_nummer,
            'beschreibung': material.beschreibung,
            'kategorie': material.kategorie,
            'einheit': material.einheit,
            'lagerbestand': material.lagerbestand,
            'mindestbestand': material.mindestbestand
        })
    
    return jsonify({'results': results})

@app.route('/admin/material_catalog')
def admin_material_catalog():
    """Admin-Bereich für Material-Katalog-Verwaltung"""
    if 'user' not in session or session['user'] not in ['nils', 'Admin']:
        return redirect(url_for('login'))
    
    materials = MaterialCatalog.query.order_by(MaterialCatalog.kategorie, MaterialCatalog.beschreibung).all()
    return render_template('admin_material_catalog.html', materials=materials)

@app.route('/admin/add_catalog_material', methods=['POST'])
def add_catalog_material():
    """Fügt neues Material zum Katalog hinzu"""
    if 'user' not in session or session['user'] not in ['nils', 'Admin']:
        return redirect(url_for('login'))
    
    try:
        material = MaterialCatalog(
            mm_nummer=request.form['mm_nummer'].strip(),
            beschreibung=request.form['beschreibung'].strip(),
            kategorie=request.form.get('kategorie', '').strip(),
            einheit=request.form.get('einheit', 'Stück'),
            standard_lieferant=request.form.get('lieferant', '').strip(),
            durchschnittspreis=float(request.form.get('preis', 0) or 0),
            lagerbestand=int(request.form.get('lagerbestand', 0) or 0),
            mindestbestand=int(request.form.get('mindestbestand', 1) or 1)
        )
        
        db.session.add(material)
        db.session.commit()
        flash(f'Material {material.mm_nummer} zum Katalog hinzugefügt.', 'success')
        
    except Exception as e:
        flash(f'Fehler beim Hinzufügen: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('admin_material_catalog'))

@app.route('/material_statistics')
def material_statistics():
    """Material-Statistiken für Dashboard"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Häufigste Materialien
    from sqlalchemy import func
    most_used = db.session.query(
        MaterialItem.mm_nummer,
        MaterialItem.beschreibung,
        func.count(MaterialItem.id).label('count')
    ).group_by(MaterialItem.mm_nummer, MaterialItem.beschreibung)\
     .order_by(func.count(MaterialItem.id).desc())\
     .limit(10).all()
    
    # Material-Kosten pro Monat
    current_month = datetime.now(timezone.utc).replace(day=1)
    monthly_costs = db.session.query(
        func.sum(MaterialItem.kosten).label('total_cost')
    ).filter(MaterialItem.bestellt_am >= current_month).scalar() or 0
    
    # Offene Bestellungen
    pending_orders = MaterialItem.query.filter(
        MaterialItem.bestellt == True,
        MaterialItem.geliefert == False
    ).count()
    
    stats = {
        'most_used_materials': most_used,
        'monthly_costs': monthly_costs,
        'pending_orders': pending_orders
    }
    
    return render_template('material_statistics.html', stats=stats)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
    # App für Netzwerkzugriff konfigurieren (von iPhone erreichbar)
    # SICHERHEIT: Debug-Modus nur in Entwicklung verwenden
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)