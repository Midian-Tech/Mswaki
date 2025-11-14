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
    plate_number = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="available")
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    driver = db.relationship("User", backref="vehicles", lazy=True)

    last_maintenance = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Vehicle {self.plate_number}>"
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'))
    pickup = db.Column(db.String(100))
    destination = db.Column(db.String(100))
    route = db.Column(db.String(100))
    reason = db.Column(db.String(200))
    status = db.Column(db.String(50))
    booking_date = db.Column(db.DateTime) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Add these relationships
    user = db.relationship("User", backref="bookings")
    vehicle = db.relationship("Vehicle", backref="bookings")


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
    trips = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)

    driver = db.relationship("User", backref="daily_collections")

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
    status = db.Column(db.String(20), nullable=False, default="Pending")

    # ✅ FIX: change Driver → User
    driver = db.relationship("User", backref="leave_requests", lazy=True)

    def __repr__(self):
        return f"<LeaveRequest driver={self.driver_id}, {self.start_date} - {self.end_date}>"
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