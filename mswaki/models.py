from mswaki import db, login_manager
from flask_login import UserMixin
from datetime import datetime,date

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f"<User {self.email}>"
    rating = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(10), default='active') 



class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), unique=True, nullable=False)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    color = db.Column(db.String(30))
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="available")
    insurance_number = db.Column(db.String(50))
    insurance_expiry = db.Column(db.Date)
    registration_number = db.Column(db.String(50))
    registration_expiry = db.Column(db.Date)
    last_maintenance = db.Column(db.DateTime, nullable=True)
    next_maintenance = db.Column(db.DateTime, nullable=True)
    odometer_reading = db.Column(db.Integer, default=0)
    fuel_type = db.Column(db.String(20), default="Petrol")
    transmission = db.Column(db.String(20), default="Automatic")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationships
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    driver = db.relationship("User", backref=db.backref('assigned_vehicles', lazy=True))
    
    def __repr__(self):
        return f"<Vehicle {self.plate_number} - {self.make} {self.model} ({self.year})>"
        
    def to_dict(self):
        return {
            'id': self.id,
            'plate_number': self.plate_number,
            'make': self.make,
            'model': self.model,
            'year': self.year,
            'color': self.color,
            'capacity': self.capacity,
            'status': self.status,
            'driver_id': self.driver_id,
            'driver_name': self.driver.name if self.driver else None,
            'insurance_number': self.insurance_number,
            'insurance_expiry': self.insurance_expiry.isoformat() if self.insurance_expiry else None,
            'registration_number': self.registration_number,
            'registration_expiry': self.registration_expiry.isoformat() if self.registration_expiry else None,
            'last_maintenance': self.last_maintenance.isoformat() if self.last_maintenance else None,
            'next_maintenance': self.next_maintenance.isoformat() if self.next_maintenance else None,
            'odometer_reading': self.odometer_reading,
            'fuel_type': self.fuel_type,
            'transmission': self.transmission,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seats = db.Column(db.Integer, nullable=False)
    pickup = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    route = db.Column(db.String(100))  # optional
    reason = db.Column(db.String(200))
    status = db.Column(db.String(50), default="Pending")
    
    booking_date = db.Column(db.DateTime)  # when the ride is requested
    travel_date = db.Column(db.Date)       # new: day of travel
    travel_time = db.Column(db.Time)       # new: time of travel
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    rejection_reason = db.Column(db.String(200))

    user = db.relationship("User", backref="bookings")
class Maintenance(db.Model):
    __tablename__ = "maintenance"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    vehicle = db.relationship("Vehicle", backref="maintenance_records", lazy=True)

    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    driver = db.relationship("User", backref="maintenance_reports", lazy=True)

    description = db.Column(db.String(255), nullable=False)

    reported_cost = db.Column(db.Float, default=0.0)  # cost provided by driver
    actual_cost   = db.Column(db.Float, default=0.0)  # cost admin enters after completion

    date_reported = db.Column(db.DateTime, default=datetime.utcnow)
    date_completed = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(50), default="Pending")

    def __repr__(self):
        return f"<Maintenance vehicle={self.vehicle_id}, status={self.status}>"



class DailyCollection(db.Model):
    __tablename__ = "daily_collection"

    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    trips = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    notes = db.Column(db.Text, nullable=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    driver = db.relationship("User", foreign_keys=[driver_id], backref="daily_collections")
    vehicle = db.relationship("Vehicle", backref="daily_collections")
    recorded_by_user = db.relationship("User", foreign_keys=[recorded_by])

    def __repr__(self):
        return f"<DailyCollection driver={self.driver_id}, date={self.date}, amount={self.amount}>"


class LeaveRequest(db.Model):
    __tablename__ = "leave_request"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    request_date = db.Column(db.Date, nullable=False, default=date.today)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    processed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    driver = db.relationship("User", backref="leave_requests", lazy=True, foreign_keys=[driver_id])
    processed_by_user = db.relationship("User", foreign_keys=[processed_by], lazy=True)


class Expense(db.Model):
    __tablename__ = "expense"
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(100), nullable=False)  # e.g., 'fuel', 'maintenance', 'salaries', 'other'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    receipt_number = db.Column(db.String(100), nullable=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    recorded_by_user = db.relationship("User", backref="expenses_recorded")
    vehicle = db.relationship("Vehicle", backref="expenses")
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'category': self.category,
            'amount': self.amount,
            'description': self.description,
            'receipt_number': self.receipt_number,
            'vehicle_id': self.vehicle_id,
            'vehicle_plate': self.vehicle.plate_number if self.vehicle else 'N/A',
            'recorded_by': self.recorded_by_user.name,
            'created_at': self.created_at.isoformat()}


class MisbehaviorReport(db.Model):
    __tablename__ = 'misbehavior_report'

    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=True)
    description = db.Column(db.Text, nullable=False)
    date_reported = db.Column(db.DateTime, default=datetime.utcnow)
    reporter_type = db.Column(db.String(20), default='passenger')
    status = db.Column(db.String(20), default='Pending')
    passenger = db.relationship('User', foreign_keys=[passenger_id], backref='reports_made', lazy=True)
    driver = db.relationship('User', foreign_keys=[driver_id], backref='reports_against', lazy=True)
    vehicle = db.relationship('Vehicle', backref='misbehavior_reports', lazy=True)

    def __repr__(self):
        return f"<MisbehaviorReport {self.id} - {self.status}>"