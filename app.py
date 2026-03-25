import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = "WanderSync-super-secret-key"

# ==========================================
# FILE UPLOAD CONFIGURATION
# ==========================================
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///WanderSync.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ==========================================
# STATIC "AI" DATABASE (Replaces Live API)
# ==========================================
# This dictionary simulates an AI. If the destination matches, it returns this premium data.
STATIC_DESTINATION_DB = {
    "tadoba andhari tiger reserve": {
        "places": ["Moharli Gate Core Zone", "Taru Pench Buffer", "Irai Lake"],
        "food": ["Tadoba Jungle Camp Dining", "Local Varhadi Thali", "Tiger Trails Restaurant"],
        "shopping": ["Local Bamboo Handicrafts", "Tribal Art Emporium"],
        "hotels": ["Svasara Jungle Lodge", "Tadoba Tiger King Resort", "MTDC Moharli"],
        "parking": "Secure parking is available at all official safari lodge gates.",
        "itinerary": [
            "Day 1: Arrive, check into your wildlife lodge, and enjoy a relaxed evening nature walk.",
            "Day 2: Early morning 5:30 AM open-jeep safari in the Core Zone, afternoon rest, and evening buffer zone safari.",
            "Day 3: Breakfast with forest views and departure."
        ]
    },
    "goa": {
        "places": ["Dudhsagar Waterfalls", "Aguada Fort", "Basilica of Bom Jesus"],
        "food": ["The Fisherman's Wharf", "Curlies Beach Shack", "Gunpowder"],
        "shopping": ["Anjuna Flea Market", "Mapusa Friday Market"],
        "hotels": ["Taj Exotica Resort & Spa", "W Goa", "The Leela"],
        "parking": "Rent a scooter! Four-wheeler parking near popular beaches is very limited.",
        "itinerary": [
            "Day 1: Arrive in North Goa, settle into your beach resort, and watch the sunset at Baga Beach.",
            "Day 2: Morning visit to Aguada Fort, afternoon watersports, and an evening seafood dinner.",
            "Day 3: Explore the historic churches of Old Goa before departure."
        ]
    },
    "manali": {
        "places": ["Solang Valley", "Rohtang Pass", "Hadimba Devi Temple"],
        "food": ["Johnson's Cafe", "Cafe 1947", "The Lazy Dog"],
        "shopping": ["Mall Road", "Old Manali Market"],
        "hotels": ["The Himalayan", "Span Resort and Spa", "Shivadya Resort"],
        "parking": "Traffic on Mall Road is restricted; rely on hotel parking or designated public lots.",
        "itinerary": [
            "Day 1: Arrive in Manali, acclimatize, and take a stroll down Mall Road.",
            "Day 2: Full day adventure trip to Solang Valley for paragliding and skiing.",
            "Day 3: Visit Hadimba Temple and Vashisht Village before heading home."
        ]
    },
    "jaipur": {
        "places": ["Amber Fort", "Hawa Mahal", "City Palace"],
        "food": ["Chokhi Dhani", "Laxmi Mishthan Bhandar (LMB)", "1135 AD"],
        "shopping": ["Johari Bazaar", "Bapu Bazaar"],
        "hotels": ["Rambagh Palace", "Taj Jai Mahal Palace", "Samode Haveli"],
        "parking": "Use paid parking lots near the major bazaars, as street parking is heavily congested.",
        "itinerary": [
            "Day 1: Arrive in the Pink City, check into your heritage haveli, and visit Hawa Mahal at sunset.",
            "Day 2: Morning elephant ride at Amber Fort, followed by afternoon shopping in Johari Bazaar.",
            "Day 3: Explore the City Palace and Jantar Mantar before departure."
        ]
    }
}

def generate_dynamic_fallback(destination):
    """If the user searches a city not in our dictionary, this builds a fake AI response using their city name."""
    dest = destination.title()
    return {
        "places": [f"Historic {dest} Downtown", f"{dest} Central Museum", f"Scenic {dest} Viewpoint"],
        "food": [f"Traditional {dest} Bistro", "The Spice Lounge", f"Central Cafe {dest}"],
        "shopping": [f"{dest} Main Street Market", "Heritage Mall"],
        "hotels": [f"The Grand {dest} Hotel", f"{dest} Boutique Resort"],
        "parking": f"Public transit is recommended in the {dest} center, though hotel parking is widely available.",
        "itinerary": [
            f"Day 1: Arrival in {dest}, check-in, and an evening walk around the city center.",
            f"Day 2: Full day exploring {dest}'s top sights and local culinary scene.",
            f"Day 3: Souvenir shopping in {dest} and departure."
        ]
    }

# ==========================================
# DATABASE MODELS
# ==========================================
class Trip(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    origin = db.Column(db.String(100))
    destination = db.Column(db.String(100), nullable=False)
    dates = db.Column(db.String(100))
    budget = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    
    itinerary = db.Column(db.JSON, default=list)
    packing_list = db.Column(db.JSON, default=list)
    ai_recommendations = db.Column(db.JSON, default=dict) 
    
    expenses = db.relationship('Expense', backref='trip', lazy=True, cascade="all, delete-orphan")
    booking = db.relationship('Booking', backref='trip', uselist=False, cascade="all, delete-orphan")

    @property
    def total_spent(self): return sum(e.cost for e in self.expenses)
    @property
    def remaining_budget(self): return self.budget - self.total_spent
    @property
    def spent_pct(self): return min(round((self.total_spent / self.budget) * 100, 1), 100) if self.budget > 0 else 0

class Expense(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    cost = db.Column(db.Integer, nullable=False)
    trip_id = db.Column(db.String(36), db.ForeignKey('trip.id'), nullable=False)

class Document(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    original_name = db.Column(db.String(255), nullable=False)
    saved_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(10))
    size_kb = db.Column(db.Integer)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

class Booking(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    trip_id = db.Column(db.String(36), db.ForeignKey('trip.id'), nullable=False)
    travel_mode = db.Column(db.String(50))
    accommodation = db.Column(db.String(100))
    passengers = db.Column(db.Integer, default=1)
    payment_method = db.Column(db.String(50))
    status = db.Column(db.String(50), default="Confirmed")
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# CORE ROUTES (TRIP PLANNER)
# ==========================================
@app.route('/')
def home():
    trips = Trip.query.all()
    return render_template('index.html', trips=trips)

@app.route('/add_trip', methods=['POST'])
def add_trip():
    start_raw = request.form.get('start_date')
    end_raw = request.form.get('end_date')
    try:
        s_date = datetime.strptime(start_raw, '%Y-%m-%d')
        e_date = datetime.strptime(end_raw, '%Y-%m-%d')
        formatted_dates = f"{s_date.strftime('%b %d')} – {e_date.strftime('%b %d, %Y')}"
    except:
        formatted_dates = "Dates not set"

    new_trip = Trip(
        id=str(uuid.uuid4()), origin=request.form.get('origin', '').strip(),
        destination=request.form.get('destination', '').strip(), dates=formatted_dates,
        budget=int(request.form.get('budget', 0)), notes=request.form.get('notes', '').strip(),
        itinerary=[], packing_list=[], ai_recommendations={}
    )
    db.session.add(new_trip)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/delete_trip/<trip_id>', methods=['POST'])
def delete_trip(trip_id):
    trip = Trip.query.get(trip_id)
    if trip:
        db.session.delete(trip)
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/add_expense/<trip_id>', methods=['POST'])
def add_expense(trip_id):
    trip = Trip.query.get(trip_id)
    if trip:
        new_expense = Expense(id=str(uuid.uuid4()), item=request.form.get('item', '').strip(), cost=int(request.form.get('cost', 0)), trip_id=trip.id)
        db.session.add(new_expense)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/delete_expense/<trip_id>/<expense_id>', methods=['POST'])
def delete_expense(trip_id, expense_id):
    expense = Expense.query.get(expense_id)
    if expense:
        db.session.delete(expense)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/add_plan/<trip_id>', methods=['POST'])
def add_plan(trip_id):
    trip = Trip.query.get(trip_id)
    if trip and request.form.get('plan', '').strip():
        updated_itinerary = list(trip.itinerary)
        updated_itinerary.append(request.form.get('plan', '').strip())
        trip.itinerary = updated_itinerary
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/delete_plan/<trip_id>/<int:index>', methods=['POST'])
def delete_plan(trip_id, index):
    trip = Trip.query.get(trip_id)
    if trip and 0 <= index < len(trip.itinerary):
        updated_itinerary = list(trip.itinerary)
        updated_itinerary.pop(index)
        trip.itinerary = updated_itinerary
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/update_notes/<trip_id>', methods=['POST'])
def update_notes(trip_id):
    trip = Trip.query.get(trip_id)
    if trip:
        trip.notes = request.form.get('notes', '').strip()
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/generate_packing/<trip_id>', methods=['POST'])
def generate_packing(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip: return redirect(request.referrer or url_for('home'))
    
    # STATIC FAKE AI PACKING LIST
    dest = trip.destination.title()
    trip.packing_list = [
        "Comfortable walking shoes",
        f"Travel guide & maps for {dest}",
        "Power bank and universal adapter",
        "Weather-appropriate clothing layers",
        "Sunscreen and sunglasses",
        "First-aid kit and personal medications",
        "Reusable water bottle",
        "Camera or smartphone with extra storage"
    ]
    db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/clear_packing/<trip_id>', methods=['POST'])
def clear_packing(trip_id):
    trip = Trip.query.get(trip_id)
    if trip:
        trip.packing_list = []
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

# --- STATIC "AI" RECOMMENDATIONS ROUTE ---
@app.route('/trip/<trip_id>')
def trip_details(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip:
        return redirect(url_for('home'))
    
    # If the trip doesn't have saved recommendations yet, generate them statically
    if not trip.ai_recommendations:
        dest_lower = trip.destination.lower()
        
        # Check if the destination exists in our hardcoded dictionary (e.g. "goa" in "south goa")
        match_found = False
        for key, data in STATIC_DESTINATION_DB.items():
            if key in dest_lower:
                trip.ai_recommendations = data
                match_found = True
                break
        
        # If it's a completely random place, use the dynamic fallback
        if not match_found:
            trip.ai_recommendations = generate_dynamic_fallback(trip.destination)
            
        # Save it so it's permanent
        db.session.commit() 

    return render_template('details.html', trip=trip, recommendations=trip.ai_recommendations)

# ==========================================
# BOOKING ROUTES
# ==========================================
@app.route('/book/<trip_id>')
def book_trip(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip: return redirect(url_for('home'))
    if trip.booking:
        flash("This trip is already booked!")
        return redirect(url_for('trip_details', trip_id=trip.id))
    return render_template('booking.html', trip=trip)

@app.route('/process_booking/<trip_id>', methods=['POST'])
def process_booking(trip_id):
    trip = Trip.query.get(trip_id)
    if trip and not trip.booking:
        new_booking = Booking(
            id=str(uuid.uuid4()),
            trip_id=trip.id,
            travel_mode=request.form.get('travel_mode'),
            accommodation=request.form.get('accommodation'),
            passengers=int(request.form.get('passengers', 1)),
            payment_method=request.form.get('payment_method')
        )
        db.session.add(new_booking)
        
        booking_fee = Expense(
            id=str(uuid.uuid4()),
            item=f"Booking: {new_booking.travel_mode} & {new_booking.accommodation}",
            cost=int(request.form.get('estimated_cost', 0)),
            trip_id=trip.id
        )
        db.session.add(booking_fee)
        db.session.commit()
        flash("Booking confirmed successfully! Your tickets will be available in the Documents vault soon.")
        
    return redirect(url_for('trip_details', trip_id=trip.id))

# ==========================================
# DOCUMENTS VAULT ROUTES
# ==========================================
@app.route('/documents')
def documents():
    unlocked = session.get('docs_unlocked', False)
    docs = Document.query.order_by(Document.upload_date.desc()).all() if unlocked else []
    return render_template('documents.html', unlocked=unlocked, documents=docs)

@app.route('/unlock_docs', methods=['POST'])
def unlock_docs():
    if request.form.get('password') == 'Docpass': session['docs_unlocked'] = True
    else: flash("Incorrect vault password.")
    return redirect(url_for('documents'))

@app.route('/lock_docs', methods=['POST'])
def lock_docs():
    session.pop('docs_unlocked', None)
    return redirect(url_for('documents'))

@app.route('/upload_doc', methods=['POST'])
def upload_doc():
    if not session.get('docs_unlocked'): return redirect(url_for('documents'))
    if 'document' not in request.files: return redirect(url_for('documents'))
    file = request.files['document']
    if file.filename == '': return redirect(url_for('documents'))

    if file and allowed_file(file.filename):
        original_name = secure_filename(file.filename)
        file_ext = original_name.rsplit('.', 1)[1].lower()
        doc_id = str(uuid.uuid4())
        saved_name = f"{doc_id}.{file_ext}"
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_name)
        file.save(file_path)
        size_kb = os.path.getsize(file_path) // 1024
        
        new_doc = Document(id=doc_id, original_name=original_name, saved_name=saved_name, file_type=file_ext, size_kb=size_kb)
        db.session.add(new_doc)
        db.session.commit()
    return redirect(url_for('documents'))

@app.route('/download_doc/<doc_id>')
def download_doc(doc_id):
    if not session.get('docs_unlocked'): return redirect(url_for('documents'))
    doc = Document.query.get(doc_id)
    if doc: return send_from_directory(app.config['UPLOAD_FOLDER'], doc.saved_name, as_attachment=True, download_name=doc.original_name)
    return redirect(url_for('documents'))

@app.route('/delete_doc/<doc_id>', methods=['POST'])
def delete_doc(doc_id):
    if not session.get('docs_unlocked'): return redirect(url_for('documents'))
    doc = Document.query.get(doc_id)
    if doc:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc.saved_name)
        if os.path.exists(file_path): os.remove(file_path)
        db.session.delete(doc)
        db.session.commit()
    return redirect(url_for('documents'))

# ==========================================
# ADMIN DATABASE VIEWER
# ==========================================
@app.route('/admin')
def admin_dashboard():
    # Fetch everything from the database
    all_trips = Trip.query.all()
    all_bookings = Booking.query.all()
    all_expenses = Expense.query.all()
    all_documents = Document.query.all()
    
    return render_template('admin.html', 
                           trips=all_trips, 
                           bookings=all_bookings, 
                           expenses=all_expenses, 
                           documents=all_documents)

if __name__ == '__main__':
    app.run(debug=True)