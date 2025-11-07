from flask import (
    Blueprint, render_template, redirect, url_for,
    request, flash, session
)
from datetime import datetime,date

from flask_login import current_user
from werkzeug.security import check_password_hash, generate_password_hash
from mswaki import db
from mswaki.models import User, Booking, Vehicle, Maintenance, MisbehaviorReport
from mswaki.models import LeaveRequest
from functools import wraps
from flask import session, flash, redirect, url_for
# ============================================================
# BLUEPRINT SETUP
# ============================================================
routes = Blueprint("routes", __name__)

# ============================================================
# LOGIN REQUIRED DECORATOR
# ============================================================
def login_required(role=None):
    """
    Custom login + role-based access decorator.
    Ensures a user is logged in, and optionally checks their role.
    Redirects unauthorized users to appropriate dashboards or login page.
    """
    def decorator(f):
        @wraps(f)  # 🧠 preserves original function metadata (critical)
        def decorated_function(*args, **kwargs):
            # Check login status
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("routes.login"))

            # Check role if specified
            user_role = session.get("role")
            if role and user_role != role:
                flash("You are not authorized to access this page.", "danger")

                # Redirect based on user role
                if user_role == "admin":
                    return redirect(url_for("routes.admin_dashboard"))
                elif user_role == "driver":
                    return redirect(url_for("routes.driver_dashboard"))
                else:
                    return redirect(url_for("routes.user_dashboard"))

            # ✅ Everything okay — allow access
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
            session["user_id"] = user.id
            session["role"] = user.role
            session["name"] = user.name
            flash(f"Welcome back, {user.name}!", "success")
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
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("routes.login"))

# ============================================================
# ADMIN ROUTES
# ============================================================
@routes.route("/admin/dashboard")
@login_required(role="admin")
def admin_dashboard():
    stats = {
        "today_revenue": "12,500",
        "today_trips": 56,
        "month_profit": "385,000",
        "month_maintenance": "45,000",
        "active_vehicles": Vehicle.query.filter_by(status="available").count(),
        "vehicles_on_leave": 2,
        "pending_leaves": 1
    }
    bookings = Booking.query.order_by(Booking.created_at.desc()).limit(10).all()
    return render_template("admin_dashboard.html", stats=stats, bookings=bookings)

@routes.route("/admin/bookings")
@login_required(role="admin")
def admin_bookings():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    return render_template("admin_bookings.html", bookings=bookings)

@routes.route("/admin/drivers")
@login_required(role="admin")
def admin_drivers():
    drivers = User.query.filter_by(role="driver").all()
    vehicles = Vehicle.query.all()
    return render_template("admin_drivers.html", drivers=drivers, vehicles=vehicles)

@routes.route("/admin/finance")
@login_required(role="admin")
def admin_finance():
    # Placeholder for finance logic
    return render_template("admin_finance.html")

@routes.route("/admin/maintenance")
@login_required(role="admin")
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

@routes.route("/admin/settings", methods=["GET", "POST"])
@login_required(role="admin")
def admin_settings():
    admin = User.query.get(session["user_id"])
    if request.method == "POST":
        admin.name = request.form.get("name")
        admin.email = request.form.get("email")
        db.session.commit()
        flash("Settings updated successfully.", "success")
        return redirect(url_for("routes.admin_settings"))
    return render_template("admin_settings.html", admin=admin)

@routes.route("/admin/misbehavior_reports")
@login_required(role="admin")
def admin_misbehavior_reports():
    reports = MisbehaviorReport.query.order_by(MisbehaviorReport.date_reported.desc()).all()
    users = {u.id: u.name for u in User.query.all()}
    return render_template("admin_misbehavior.html", reports=reports, users=users)

@routes.route("/admin/resolve_report/<int:report_id>", methods=["POST"])
@login_required(role="admin")
def resolve_report(report_id):
    report = MisbehaviorReport.query.get_or_404(report_id)
    report.status = "resolved"
    db.session.commit()
    flash(f"Report #{report.id} marked as resolved.", "success")
    return redirect(url_for("routes.admin_misbehavior_reports"))

# ============================================================
# ADMIN DRIVER & VEHICLE MANAGEMENT
# ============================================================
@routes.route("/add_driver", methods=["POST"])
@login_required(role="admin")
def add_driver():
    name = request.form.get("name")
    email = request.form.get("email")
    password = request.form.get("password")
    if not (name and email and password):
        flash("All fields are required.", "danger")
        return redirect(url_for("routes.admin_drivers"))
    if User.query.filter_by(email=email).first():
        flash("Email already registered.", "warning")
        return redirect(url_for("routes.admin_drivers"))
    driver = User(name=name, email=email, password=generate_password_hash(password), role="driver")
    db.session.add(driver)
    db.session.commit()
    flash("Driver added successfully!", "success")
    return redirect(url_for("routes.admin_drivers"))

@routes.route("/remove_driver/<int:driver_id>", methods=["POST"])
@login_required(role="admin")
def remove_driver(driver_id):
    driver = User.query.get_or_404(driver_id)
    db.session.delete(driver)
    db.session.commit()
    flash(f"Driver {driver.name} removed successfully.", "success")
    return redirect(url_for("routes.admin_drivers"))

@routes.route("/add_vehicle", methods=["POST"])
@login_required(role="admin")
def add_vehicle():
    plate_number = request.form.get("plate_number")
    driver_id = request.form.get("driver_id")
    status = request.form.get("status")
    if not (plate_number and driver_id):
        flash("All fields are required.", "danger")
        return redirect(url_for("routes.admin_drivers"))
    try:
        driver_id = int(driver_id)
        vehicle = Vehicle(plate_number=plate_number, driver_id=driver_id, status=status)
        db.session.add(vehicle)
        db.session.commit()
        flash("Vehicle added successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding vehicle: {str(e)}", "danger")
    return redirect(url_for("routes.admin_drivers"))

@routes.route("/admin/delete_vehicle/<int:vehicle_id>", methods=["POST"])
@login_required(role="admin")
def delete_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    db.session.delete(vehicle)
    db.session.commit()
    flash("Vehicle deleted successfully.", "info")
    return redirect(url_for("routes.admin_drivers"))

# ------------------ RATE DRIVER ------------------
@routes.route("/rate_driver/<int:driver_id>", methods=["POST"])
@login_required()
def rate_driver(driver_id):
    rating = request.form.get("rating")
    driver = User.query.get_or_404(driver_id)
    try:
        driver.rating = float(rating)
        db.session.commit()
        flash(f"Driver {driver.name} rated {rating} stars.", "success")
    except Exception:
        db.session.rollback()
        flash("Failed to rate driver.", "danger")
    return redirect(request.referrer or url_for("routes.admin_drivers"))
@routes.route("/admin/reports")
@login_required(role="admin")
def admin_reports():
    """Admin summary reports page (statistics overview)"""
    total_users = User.query.count()
    total_drivers = User.query.filter_by(role="driver").count()
    total_bookings = Booking.query.count()
    total_vehicles = Vehicle.query.count()
    maintenance_count = Maintenance.query.count()
    unresolved_reports = MisbehaviorReport.query.filter_by(status="pending").count()

    stats = {
        "total_users": total_users,
        "total_drivers": total_drivers,
        "total_bookings": total_bookings,
        "total_vehicles": total_vehicles,
        "maintenance": maintenance_count,
        "unresolved_reports": unresolved_reports,
    }

    return render_template("admin_reports.html", stats=stats)

# ============================================================
# DRIVER ROUTES
# ============================================================

@routes.route("/driver/dashboard")
@login_required(role="driver")
def driver_dashboard():
    """Show driver dashboard with latest maintenance reports"""
    driver_id = session.get("user_id")

    # Get vehicles assigned to this driver
    vehicles = Vehicle.query.filter_by(driver_id=driver_id).all()
    vehicle_ids = [v.id for v in vehicles]

    # Fetch recent maintenance reports related to driver vehicles
    maintenance = Maintenance.query.filter(Maintenance.vehicle_id.in_(vehicle_ids))\
        .order_by(Maintenance.date_reported.desc()).limit(10).all()

    return render_template("driver_dashboard.html", maintenance=maintenance, vehicles=vehicles)


@routes.route("/driver/report_maintenance", methods=["GET", "POST"])
@login_required(role="driver")
def report_maintenance():
    """Allow driver to report a maintenance issue"""
    driver_id = session.get("user_id")

    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id")
        description = request.form.get("description")

        if not (vehicle_id and description):
            flash("All fields are required.", "danger")
            return redirect(url_for("routes.report_maintenance"))

        maintenance = Maintenance(
            vehicle_id=vehicle_id,
            description=description,
            date_reported=datetime.now(),
            status="Ongoing"
        )
        db.session.add(maintenance)

        # Optionally mark vehicle as "In Maintenance"
        vehicle = Vehicle.query.get(vehicle_id)
        if vehicle:
            vehicle.status = "In Maintenance"

        db.session.commit()
        flash("Maintenance issue reported successfully!", "success")
        return redirect(url_for("routes.driver_dashboard"))

    # Fetch driver’s assigned vehicles
    vehicles = Vehicle.query.filter_by(driver_id=driver_id).all()
    return render_template("report_maintenance.html", vehicles=vehicles)


@routes.route("/driver/daily_collection", methods=["GET", "POST"])
@login_required(role="driver")
def driver_daily_collection():
    driver_id = session.get("user_id")

    from mswaki.models import DailyCollection

    if request.method == "POST":
        trips = request.form.get("trips")
        amount = request.form.get("amount")
        collection_date = request.form.get("date")

        # Check all required fields
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

        # ✅ Only check for existing after collection_date is defined
        existing = DailyCollection.query.filter_by(driver_id=driver_id, date=collection_date).first()
        if existing:
            flash("You already submitted a collection for this date.", "warning")
            return redirect(url_for("routes.driver_daily_collection"))

        collection = DailyCollection(
            driver_id=driver_id,
            trips=trips,
            amount=amount,
            date=collection_date
        )
        db.session.add(collection)
        db.session.commit()
        flash("Daily collection recorded successfully!", "success")
        return redirect(url_for("routes.driver_daily_collection"))

    # Fetch latest collections for GET requests
    collections = DailyCollection.query.filter_by(driver_id=driver_id)\
        .order_by(DailyCollection.date.desc()).limit(10).all()

    return render_template(
        "driver_daily_collection.html",
        collections=collections,
        today=date.today().isoformat()
    )

@routes.route('/driver/leave_requests', methods=['GET', 'POST'])
@login_required(role="driver")
def driver_leave_requests():
    """Driver Leave Requests — view and submit leave requests."""

    driver_id = session.get("user_id")

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        leave_type = request.form.get('leave_type')
        reason = request.form.get('reason')

        if not (start_date_str and end_date_str and leave_type and reason):
            flash("Please fill in all required fields.", "danger")
        else:
            # ✅ Convert string -> Python date
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

    # ✅ Fetch all requests for this driver
    leave_requests = LeaveRequest.query.filter_by(driver_id=driver_id).order_by(
        LeaveRequest.request_date.desc()
    ).all()

    return render_template(
        "driver_leave_requests.html",
        leave_requests=leave_requests,
        today=date.today().isoformat()
    )
# PASSENGER ROUTES
# ============================================================
@routes.route("/user/dashboard")
@login_required(role="passenger")
def user_dashboard():
    # Show latest 10 bookings for this user
    bookings = Booking.query.filter_by(user_id=session["user_id"])\
        .order_by(Booking.created_at.desc()).limit(10).all()
    return render_template("user_dashboard.html", bookings=bookings)



@routes.route("/book_vehicle", methods=["GET", "POST"])
@login_required()
def book_vehicle():
    """
    Allows a logged-in user to book a vehicle.
    Shows only available vehicles not under maintenance or already booked.
    """
    if request.method == "POST":
        # --- Get form data ---
        vehicle_id = request.form.get("vehicle_id")
        pickup = request.form.get("pickup")
        destination = request.form.get("destination")
        reason = request.form.get("reason")

        # --- Validate input ---
        if not all([vehicle_id, pickup, destination, reason]):
            flash("Please fill in all fields before submitting.", "danger")
            return redirect(url_for("routes.book_vehicle"))

        try:
            # --- Create a new booking record ---
            booking = Booking(
                user_id=current_user.id,
                vehicle_id=int(vehicle_id),
                pickup=pickup.strip(),
                destination=destination.strip(),
                reason=reason.strip(),
                booking_date=datetime.utcnow(),
                created_at=datetime.utcnow(),
                status="Pending",
            )

            db.session.add(booking)
            db.session.commit()

            flash(" Booking request submitted successfully!", "success")
            return redirect(url_for("routes.user_dashboard"))

        except Exception as e:
            db.session.rollback()
            flash(f" Error while saving booking: {str(e)}", "danger")
            return redirect(url_for("routes.book_vehicle"))

    # --- Prepare list of available vehicles ---
    maintenance_ids = [m.vehicle_id for m in Maintenance.query.all()]
    active_booking_ids = [
        b.vehicle_id for b in Booking.query.filter(
            Booking.status.in_(["Pending", "Approved"])
        ).all()
    ]
    excluded_ids = set(maintenance_ids + active_booking_ids)

    available_vehicles = Vehicle.query.filter(
        Vehicle.status == "available",
        ~Vehicle.id.in_(excluded_ids)
    ).all()

    return render_template("book_vehicle.html", available_vehicles=available_vehicles)

@routes.route("/user/profile", methods=["GET", "POST"])
@login_required(role="passenger")
def user_profile():
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if name:
            user.name = name
        if email:
            user.email = email
        if password:
            user.password = generate_password_hash(password)

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("routes.user_profile"))

    return render_template("user_profile.html", user=user)
@routes.route("/user/report_misbehavior", methods=["GET", "POST"])
@login_required(role="passenger")
def report_misbehavior():
    if request.method == "POST":
        driver_id = request.form.get("driver_id")
        vehicle_id = request.form.get("vehicle_id")
        description = request.form.get("description")

        if not description:
            flash("Please provide details of the misbehavior.", "danger")
            return redirect(url_for("routes.report_misbehavior"))

        # ✅ Use session ID instead of current_user.id
        user_id = session.get("user_id")

        report = MisbehaviorReport(
            driver_id=int(driver_id) if driver_id else None,
            vehicle_id=int(vehicle_id) if vehicle_id else None,
            description=description,
            date_reported=datetime.now(),
            reporter_type="user" if user_id else "anonymous"
        )

        db.session.add(report)
        db.session.commit()

        flash("Your report has been submitted successfully. Thank you for helping us improve safety.", "success")
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
