from flask import (
    Blueprint, render_template, redirect, url_for,
    request, flash, session, make_response, Response
)
from datetime import datetime, date
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import func

from mswaki import db
from mswaki.models import (
    User, Booking, Vehicle, Maintenance, MisbehaviorReport,
    LeaveRequest, DailyCollection
)
import csv
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask import make_response

# ============================================================
# BLUEPRINT SETUP
# ============================================================
routes = Blueprint("routes", __name__)

# ============================================================
# ROLE-BASED ACCESS DECORATOR
# ============================================================
def role_required(role):
    """Ensure the current_user has the given role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in first.", "warning")
                return redirect(url_for("routes.login"))
            if current_user.role != role:
                flash("You are not authorized to access this page.", "danger")
                # Redirect based on role
                if current_user.role == "admin":
                    return redirect(url_for("routes.admin_dashboard"))
                elif current_user.role == "driver":
                    return redirect(url_for("routes.driver_dashboard"))
                else:
                    return redirect(url_for("routes.user_dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================================
# PUBLIC ROUTES
# ============================================================
@routes.route("/")
def home():
    return redirect(url_for("routes.login"))

@routes.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")
            # Redirect based on role
            if user.role == "admin":
                return redirect(url_for("routes.admin_dashboard"))
            elif user.role == "driver":
                return redirect(url_for("routes.driver_dashboard"))
            else:
                return redirect(url_for("routes.user_dashboard"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")

@routes.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "passenger")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return redirect(url_for("routes.register"))

        new_user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role=role
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("routes.login"))

    return render_template("register.html")

@routes.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("routes.login"))

# ============================================================
# ADMIN ROUTES
# ============================================================
@routes.route("/admin/dashboard")
@login_required
@role_required("admin")
def admin_dashboard():
    # ---- BOOKINGS ----
    bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(10).all()
    booking_data = [
        {
            "id": b.id,
            "user_name": b.user.name if b.user else "Unknown",
            "route": b.route,
            "date": b.booking_date.strftime("%Y-%m-%d"),
            "status": b.status
        } for b in bookings
    ]

    # ---- DAILY COLLECTIONS ----
    today = date.today()
    today_collections = DailyCollection.query.filter_by(date=today).all()
    today_revenue = sum(c.amount for c in today_collections)
    today_trips = sum(c.trips for c in today_collections)

    # ---- MONTHLY ----
    first_day = date(today.year, today.month, 1)
    month_collections = DailyCollection.query.filter(DailyCollection.date >= first_day).all()
    month_revenue = sum(c.amount for c in month_collections)

    # ---- MAINTENANCE COST THIS MONTH ----
    month_maintenance = db.session.query(func.sum(Maintenance.actual_cost))\
        .filter(Maintenance.status == "Completed", Maintenance.date_reported >= first_day).scalar() or 0
    month_profit = month_revenue - month_maintenance

    # ---- VEHICLE STATS ----
    active_vehicles = Vehicle.query.filter_by(status="Active").count()
    vehicles_on_leave = Vehicle.query.filter_by(status="On Leave").count()

    # ---- LEAVE STATS ----
    pending_leaves = LeaveRequest.query.filter_by(status="Pending").count()

    # ---- MISBEHAVIOR reports count ----
    misbehavior_count = MisbehaviorReport.query.count()

    stats = {
        "today_revenue": today_revenue,
        "today_trips": today_trips,
        "month_profit": month_profit,
        "month_maintenance": month_maintenance,
        "active_vehicles": active_vehicles,
        "vehicles_on_leave": vehicles_on_leave,
        "pending_leaves": pending_leaves,
        "misbehavior_reports": misbehavior_count
    }

    return render_template("admin_dashboard.html", stats=stats, bookings=booking_data)


# =================== ADMIN EXPORT CSV =====================
@routes.route("/admin/export_csv")
@login_required
@role_required("admin")
def export_csv():
    collections = DailyCollection.query.all()

    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Driver", "Trips", "Amount", "Vehicle", "Date"])

    for c in collections:
        writer.writerow([
            c.driver.name if c.driver else "N/A",
            c.trips,
            c.amount,
            c.driver.vehicle.plate_number if c.driver and c.driver.vehicle else "N/A",
            c.date
        ])

    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=finance_report.csv"}
    )

@routes.route("/admin/finance")
@login_required
@role_required("admin")
def admin_finance():
    collections = db.session.query(
        DailyCollection.date,
        User.name.label("driver_name"),
        Vehicle.plate_number.label("vehicle_plate"),
        DailyCollection.amount
    ).join(User, User.id == DailyCollection.driver_id)\
     .join(Vehicle, Vehicle.driver_id == User.id).all()

    monthly_revenue = {}
    for c in collections:
        month = c.date.strftime("%B %Y")
        monthly_revenue.setdefault(month, 0)
        monthly_revenue[month] += c.amount

    total_expenses = db.session.query(func.sum(Maintenance.actual_cost)).scalar() or 0.0

    total_revenue = sum(monthly_revenue.values())
    profit = total_revenue - total_expenses

    chart_data = [{"month": str(m), "revenue": float(r)} for m, r in monthly_revenue.items()]
    chart_data.sort(key=lambda x: datetime.strptime(x['month'], '%B %Y'))

    return render_template(
        "admin_finance.html",
        collections=collections,
        monthly_revenue=monthly_revenue,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        profit=profit,
        chart_data=chart_data
    )

@routes.route("/admin/finance/download_pdf")
@role_required(role="admin")
def download_finance_pdf():
    collections = (
        db.session.query(
            DailyCollection.date,
            User.name.label("driver_name"),
            Vehicle.plate_number.label("vehicle_plate"),
            DailyCollection.amount
        )
        .join(User, User.id == DailyCollection.driver_id)
        .join(Vehicle, Vehicle.driver_id == User.id)
        .all()
    )

    # Create a PDF in memory
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(200, height - 50, "Finance Report")

    pdf.setFont("Helvetica", 12)
    y = height - 100
    pdf.drawString(50, y, "Date")
    pdf.drawString(150, y, "Driver")
    pdf.drawString(300, y, "Vehicle")
    pdf.drawString(450, y, "Amount (KES)")
    y -= 20

    for c in collections:
        pdf.drawString(50, y, str(c.date))
        pdf.drawString(150, y, str(c.driver_name))
        pdf.drawString(300, y, str(c.vehicle_plate))
        pdf.drawString(450, y, str(c.amount))
        y -= 20
        if y < 50:
            pdf.showPage()
            y = height - 50

    pdf.save()
    buffer.seek(0)

    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=finance_report.pdf"
    return response
# ------------------ Admin maintenance ------------------
@routes.route("/admin/maintenance")
@login_required
@role_required("admin")
def admin_maintenance():
    maintenance = Maintenance.query.order_by(Maintenance.date_reported.desc()).all()
    for item in maintenance:
        if item.vehicle and item.vehicle.driver:
            item.driver_name = item.vehicle.driver.name
            item.plate_number = item.vehicle.plate_number
        else:
            item.driver_name = "Unassigned"
            item.plate_number = "N/A"
    return render_template("admin_maintenance.html", maintenance=maintenance)
@routes.route('/admin/drivers', methods=['GET'])
@role_required("admin")
def admin_drivers():
    """Display all drivers and allow admin to add vehicles/drivers"""
    drivers = User.query.filter_by(role='driver').all()
    return render_template('admin_drivers.html', drivers=drivers)

# -------------------
# ADD DRIVER
# -------------------

@routes.route('/admin/add_driver', methods=['POST'])
@role_required("admin")
def add_driver():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')

    if not name or not email or not password:
        flash("All fields are required to add a driver.", "warning")
        return redirect(url_for('routes.admin_drivers'))

    # Check for duplicate email
    if User.query.filter_by(email=email).first():
        flash("Driver with this email already exists.", "danger")
        return redirect(url_for('routes.admin_drivers'))

    new_driver = User(name=name, email=email, password=password, role='driver')
    db.session.add(new_driver)
    db.session.commit()

    flash(f"Driver {name} added successfully!", "success")
    return redirect(url_for('routes.admin_drivers'))

# -------------------
# ADD VEHICLE
# -------------------

@routes.route('/admin/add_vehicle', methods=['POST'])
@role_required("admin")
def add_vehicle():
    plate_number = request.form.get('plate_number')
    model = request.form.get('model')
    capacity = request.form.get('capacity')
    driver_id = request.form.get('driver_id')
    status = request.form.get('status', 'available')

    if not plate_number or not model or not capacity or not driver_id:
        flash("All fields are required to add a vehicle.", "warning")
        return redirect(url_for('routes.admin_drivers'))

    # Check for duplicate plate
    if Vehicle.query.filter_by(plate_number=plate_number).first():
        flash("Vehicle with this plate number already exists.", "danger")
        return redirect(url_for('routes.admin_drivers'))

    vehicle = Vehicle(
        plate_number=plate_number,
        status=status,
        driver_id=int(driver_id)
    )
    db.session.add(vehicle)
    db.session.commit()

    flash(f"Vehicle {plate_number} added successfully!", "success")
    return redirect(url_for('routes.admin_drivers'))

# -------------------
# RATE DRIVER
# -------------------

@routes.route('/admin/rate_driver/<int:driver_id>', methods=['POST'])
@role_required("admin")
def rate_driver(driver_id):
    driver = User.query.filter_by(id=driver_id, role='driver').first_or_404()
    rating = request.form.get('rating')

    try:
        rating_value = float(rating)
        if rating_value < 1 or rating_value > 5:
            raise ValueError
    except:
        flash("Rating must be a number between 1 and 5.", "danger")
        return redirect(url_for('routes.admin_drivers'))

    driver.rating = rating_value
    db.session.commit()
    flash(f"{driver.name} has been rated {rating_value} stars.", "success")
    return redirect(url_for('routes.admin_drivers'))

# -------------------
# REMOVE DRIVER
# -------------------

@routes.route('/admin/remove_driver/<int:driver_id>', methods=['POST'])
@role_required("admin")
def remove_driver(driver_id):
    driver = User.query.filter_by(id=driver_id, role='driver', status='active').first_or_404()

    # Soft-delete: deactivate driver instead of deleting
    driver.status = 'inactive'
    db.session.commit()
    flash(f"Driver {driver.name} has been deactivated.", "success")
    return redirect(url_for('routes.admin_drivers'))
@routes.route("/admin/maintenance/complete/<int:maintenance_id>", methods=["POST"])
@login_required
@role_required("admin")
def complete_maintenance(maintenance_id):
    maintenance = Maintenance.query.get_or_404(maintenance_id)
    if maintenance.status == "Completed":
        flash("This maintenance is already completed.", "info")
        return redirect(url_for("routes.admin_maintenance"))

    actual_cost = float(request.form.get("actual_cost", 0))
    maintenance.status = "Completed"
    maintenance.actual_cost = actual_cost

    vehicle = Vehicle.query.get(maintenance.vehicle_id)
    if vehicle:
        vehicle.status = "Active"

    db.session.commit()
    flash("Maintenance marked as completed.", "success")
    return redirect(url_for("routes.admin_maintenance"))

# ------------------ Admin settings ------------------
@routes.route("/admin/settings", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_settings():
    admin = current_user
    if request.method == "POST":
        admin.name = request.form.get("name")
        admin.email = request.form.get("email")
        db.session.commit()
        flash("Settings updated successfully.", "success")
        return redirect(url_for("routes.admin_settings"))
    return render_template("admin_settings.html", admin=admin)

# ------------------ Misbehavior ------------------
@routes.route("/admin/misbehavior_reports")
@role_required("admin")
def admin_misbehavior_reports():
    reports = MisbehaviorReport.query.order_by(MisbehaviorReport.date_reported.desc()).all()
    user_dict = {u.id: u.name for u in User.query.all()}  # match template
    return render_template("admin_misbehavior.html", reports=reports, user_dict=user_dict)

@routes.route("/admin/resolve_report/<int:report_id>", methods=["POST"])
@login_required
@role_required("admin")
def resolve_report(report_id):
    report = MisbehaviorReport.query.get_or_404(report_id)
    report.status = "resolved"
    db.session.commit()
    flash(f"Report #{report.id} marked as resolved.", "success")
    return redirect(url_for("routes.admin_misbehavior_reports"))

# ------------------ Admin bookings ------------------
@routes.route("/admin/bookings", methods=["GET"])
@login_required
@role_required("admin")
def admin_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template("admin_bookings.html", bookings=bookings)

@routes.route("/admin/update_booking/<int:booking_id>", methods=["POST"])
@login_required
@role_required("admin")
def admin_update_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    action = request.form.get("action")
    if action == "approve":
        booking.status = "approved"
        flash(f"Booking #{booking.id} has been approved.", "success")
    elif action == "reject":
        booking.status = "rejected"
        flash(f"Booking #{booking.id} has been rejected.", "danger")
    else:
        flash("Invalid action.", "warning")
    db.session.commit()
    return redirect(url_for("routes.admin_bookings"))

# ============================================================
# DRIVER ROUTES
# ============================================================
@routes.route("/driver/dashboard")
@login_required
@role_required("driver")
def driver_dashboard():
    driver_id = current_user.id
    vehicles = Vehicle.query.filter_by(driver_id=driver_id).all()
    vehicle_ids = [v.id for v in vehicles]

    maintenance = Maintenance.query.filter(Maintenance.vehicle_id.in_(vehicle_ids))\
        .order_by(Maintenance.date_reported.desc()).limit(10).all()
    return render_template("driver_dashboard.html", maintenance=maintenance, vehicles=vehicles)

@routes.route("/driver/report_maintenance", methods=["GET", "POST"])
@login_required
@role_required("driver")
def report_maintenance():
    driver_id = current_user.id
    vehicles = Vehicle.query.filter_by(driver_id=driver_id).all()

    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id")
        description = request.form.get("description")
        reported_cost = request.form.get("cost")
        if not (vehicle_id and description and reported_cost):
            flash("All fields are required.", "danger")
            return redirect(url_for("routes.report_maintenance"))
        try:
            reported_cost = float(reported_cost)
        except ValueError:
            flash("Please enter a valid numeric value for cost.", "danger")
            return redirect(url_for("routes.report_maintenance"))

        maintenance = Maintenance(
            vehicle_id=vehicle_id,
            driver_id=driver_id,
            description=description,
            reported_cost=reported_cost,
            date_reported=datetime.now(),
        )
        db.session.add(maintenance)

        vehicle = Vehicle.query.get(vehicle_id)
        if vehicle:
            vehicle.status = "In Maintenance"

        db.session.commit()
        flash("Maintenance issue reported successfully!", "success")
        return redirect(url_for("routes.driver_dashboard"))

    return render_template("report_maintenance.html", vehicles=vehicles)

# ------------------ Driver daily collection ------------------
@routes.route("/driver/daily_collection", methods=["GET", "POST"])
@login_required
@role_required("driver")
def driver_daily_collection():
    driver_id = current_user.id
    if request.method == "POST":
        trips = request.form.get("trips")
        amount = request.form.get("amount")
        collection_date = request.form.get("date")
        if not (trips and amount and collection_date):
            flash("All fields are required.", "danger")
            return redirect(url_for("routes.driver_daily_collection"))
        try:
            trips = int(trips)
            amount = float(amount)
            collection_date = datetime.strptime(collection_date, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid data format.", "danger")
            return redirect(url_for("routes.driver_daily_collection"))

        existing = DailyCollection.query.filter_by(driver_id=driver_id, date=collection_date).first()
        if existing:
            flash("You already submitted a collection for this date.", "warning")
            return redirect(url_for("routes.driver_daily_collection"))

        collection = DailyCollection(driver_id=driver_id, trips=trips, amount=amount, date=collection_date)
        db.session.add(collection)
        db.session.commit()
        flash("Daily collection recorded successfully!", "success")
        return redirect(url_for("routes.driver_daily_collection"))

    collections = DailyCollection.query.filter_by(driver_id=driver_id).order_by(DailyCollection.date.desc()).limit(10).all()
    return render_template("driver_daily_collection.html", collections=collections, today=date.today().isoformat())

# ------------------ Driver leave requests ------------------
@routes.route("/driver/leave_requests", methods=["GET", "POST"])
@login_required
@role_required("driver")
def driver_leave_requests():
    driver_id = current_user.id
    if request.method == "POST":
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        leave_type = request.form.get("leave_type")
        reason = request.form.get("reason")
        if not (start_date_str and end_date_str and leave_type and reason):
            flash("Please fill in all required fields.", "danger")
        else:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            leave = LeaveRequest(
                driver_id=driver_id,
                start_date=start_date,
                end_date=end_date,
                leave_type=leave_type,
                reason=reason,
                status="Pending",
                request_date=datetime.now()
            )
            db.session.add(leave)
            db.session.commit()
            flash("Leave request submitted successfully!", "success")
        return redirect(url_for('routes.driver_leave_requests'))

    leave_requests = LeaveRequest.query.filter_by(driver_id=driver_id).order_by(LeaveRequest.request_date.desc()).all()
    return render_template("driver_leave_requests.html", leave_requests=leave_requests, today=date.today().isoformat())

# ============================================================
# PASSENGER ROUTES
# ============================================================
@routes.route("/user/dashboard")
@login_required
@role_required("passenger")
def user_dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).limit(10).all()
    return render_template("user_dashboard.html", bookings=bookings)

@routes.route("/book_vehicle", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def book_vehicle():
    available_vehicles = Vehicle.query.filter_by(status="Available").all()
    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id")
        pickup = request.form.get("pickup")
        destination = request.form.get("destination")
        reason = request.form.get("reason")
        if not all([vehicle_id, pickup, destination, reason]):
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("routes.book_vehicle"))

        try:
            booking = Booking(
                user_id=current_user.id,
                vehicle_id=int(vehicle_id),
                pickup=pickup,
                destination=destination,
                reason=reason,
                status="Pending",
                booking_date=datetime.utcnow()
            )
            db.session.add(booking)
            db.session.commit()
            flash("Booking request submitted successfully!", "success")
            return redirect(url_for("routes.user_dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error while saving booking: {e}", "danger")
            return redirect(url_for("routes.book_vehicle"))

    return render_template("book_vehicle.html", available_vehicles=available_vehicles)

@routes.route("/user/profile", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def user_profile():
    user = current_user
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        if name: user.name = name
        if email: user.email = email
        if password: user.password = generate_password_hash(password)
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("routes.user_profile"))
    return render_template("user_profile.html", user=user)

@routes.route("/user/report_misbehavior", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def report_misbehavior():
    if request.method == "POST":
        driver_id = request.form.get("driver_id")
        vehicle_id = request.form.get("vehicle_id")
        description = request.form.get("description")
        if not description:
            flash("Please provide details of the misbehavior.", "danger")
            return redirect(url_for("routes.report_misbehavior"))

        report = MisbehaviorReport(
            driver_id=int(driver_id) if driver_id else None,
            vehicle_id=int(vehicle_id) if vehicle_id else None,
            description=description,
            date_reported=datetime.now(),
            reporter_type="user"
        )
        db.session.add(report)
        db.session.commit()
        flash("Your report has been submitted successfully.", "success")
        return redirect(url_for("routes.user_dashboard"))

    drivers = User.query.filter_by(role="driver").all()
    vehicles = Vehicle.query.all()
    return render_template("report_misbehavior.html", drivers=drivers, vehicles=vehicles)

# ============================================================
# ERROR HANDLERS
# ============================================================
@routes.app_errorhandler(404)
def not_found(error):
    return render_template("errors/404.html"), 404

@routes.app_errorhandler(500)
def server_error(error):
    return render_template("errors/500.html"), 500
