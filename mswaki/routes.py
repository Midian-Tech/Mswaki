from mswaki.models import DailyCollection
from flask import (
    Blueprint, app, current_app, render_template, redirect, send_file, url_for,
    request, flash, session, make_response, Response
)

import re
from datetime import datetime, date, timedelta
from datetime import datetime, date as dt_date, timedelta
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import func
import os
from mswaki import db
from mswaki.models import (
    User, Booking, Vehicle, Maintenance, MisbehaviorReport,
    LeaveRequest, DailyCollection, Expense
)
import csv
from werkzeug.utils import secure_filename
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.units import inch
from flask import make_response
import json
from flask import jsonify
from sqlalchemy import or_
from dateutil.relativedelta import relativedelta
from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

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
@role_required("admin")
def admin_dashboard():
    today = date.today()
    first_day = today.replace(day=1)
    # Last day of current month
    last_day = (first_day + relativedelta(months=1)) - timedelta(days=1)

    # --------------------------
    # TODAY'S REVENUE & TRIPS
    # --------------------------
    today_data = DailyCollection.query.filter_by(date=today).all()
    today_revenue = sum(x.amount for x in today_data)
    today_trips = sum(x.trips for x in today_data)

    # --------------------------
    # MONTHLY REVENUE & EXPENSES
    # --------------------------
    monthly_revenue = float(
        db.session.query(func.coalesce(func.sum(DailyCollection.amount), 0.0))
        .filter(DailyCollection.date.between(first_day, last_day))
        .scalar()
    )

    monthly_expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.date.between(first_day, last_day))
        .scalar()
    )

    month_profit = monthly_revenue - monthly_expenses

    # --------------------------
    # VEHICLE STATS
    # --------------------------
    active_vehicles = Vehicle.query.filter_by(status="available").count()

    vehicles_on_leave = (
        db.session.query(Vehicle)
        .join(User, User.id == Vehicle.driver_id)
        .join(LeaveRequest, LeaveRequest.driver_id == User.id)
        .filter(
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        )
        .distinct()
        .count()
    )

    pending_leaves = LeaveRequest.query.filter_by(status="pending").count()

    # --------------------------
    # DRIVER STATS
    # --------------------------
    total_drivers = User.query.filter_by(role="driver").count()
    active_drivers = User.query.filter(
        User.role == "driver",
        func.lower(User.status) == "active"
    ).count()

    # --------------------------
    # REVENUE TREND (LAST 6 MONTHS)
    # --------------------------
    revenue_data = []
    months = []
    for i in range(5, -1, -1):
        month_start = first_day - relativedelta(months=i)
        month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
        month_rev = float(
            db.session.query(func.coalesce(func.sum(DailyCollection.amount), 0.0))
            .filter(DailyCollection.date.between(month_start, month_end))
            .scalar()
        )
        revenue_data.append(month_rev)
        months.append(month_start.strftime("%b %Y"))

    # --------------------------
    # RECENT BOOKINGS
    # --------------------------
    bookings = Booking.query.order_by(Booking.created_at.desc()).limit(10).all()
    booking_list = [
        {
            "id": b.id,
            "user_name": b.user.name if b.user else "N/A",
            "route": b.route or f"{b.pickup} to {b.destination}",
            "date": b.booking_date.strftime("%Y-%m-%d") if b.booking_date else b.created_at.strftime("%Y-%m-%d"),
            "status": b.status or "N/A",
        }
        for b in bookings
    ]

    # --------------------------
    # STATS DICTIONARY
    # --------------------------
    stats = {
        "today_revenue": today_revenue,
        "today_trips": today_trips,
        "month_revenue": monthly_revenue,
        "month_expenses": monthly_expenses,
        "month_profit": month_profit,
        "active_vehicles": active_vehicles,
        "vehicles_on_leave": vehicles_on_leave,
        "pending_leaves": pending_leaves,
        "total_drivers": total_drivers,
        "active_drivers": active_drivers,
        "revenue_labels": months,
        "revenue_data": revenue_data,
    }

    return render_template("admin_dashboard.html", stats=stats, bookings=booking_list)
@routes.route('/admin/edit_driver/<int:driver_id>', methods=['GET', 'POST'])
@role_required("admin")
def edit_driver(driver_id):
    driver = User.query.filter_by(id=driver_id, role='driver').first_or_404()
    vehicles = Vehicle.query.all()

    if request.method == "POST":
        driver.name = request.form.get('name', driver.name)
        driver.email = request.form.get('email', driver.email)
        vehicle_id = request.form.get('vehicle_id')
        if vehicle_id:
            driver_vehicle = Vehicle.query.get(vehicle_id)
            driver_vehicle.driver_id = driver.id
        db.session.commit()
        flash("Driver updated successfully!", "success")
        return redirect(url_for('routes.admin_drivers'))

    return render_template('edit_driver.html', driver=driver, vehicles=vehicles)
@routes.route('/admin/edit_vehicle/<int:vehicle_id>', methods=['GET', 'POST'])
@role_required("admin")
def edit_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    drivers = User.query.filter_by(role='driver').all()

    if request.method == "POST":
        vehicle.plate_number = request.form.get('plate_number', vehicle.plate_number)
        vehicle.make = request.form.get('make', vehicle.make)
        vehicle.model = request.form.get('model', vehicle.model)
        vehicle.year = int(request.form.get('year', vehicle.year))
        vehicle.capacity = int(request.form.get('capacity', vehicle.capacity))
        driver_id = request.form.get('driver_id')
        vehicle.driver_id = int(driver_id) if driver_id else None
        db.session.commit()
        flash("Vehicle updated successfully!", "success")
        return redirect(url_for('routes.admin_vehicles'))

    return render_template('edit_vehicle.html', vehicle=vehicle, drivers=drivers)

@routes.route("/admin/leave-requests")
@role_required("admin")
def admin_leave_requests():
    # Get all leave requests, ordered by start date (newest first)
    leave_requests = LeaveRequest.query.order_by(
        LeaveRequest.start_date.desc()
    ).all()
    
    # Get pending count for the stats
    pending_count = LeaveRequest.query.filter_by(status='pending').count()
    
    return render_template(
        "admin_leave_requests.html", 
        leave_requests=leave_requests,
        stats={"pending_leaves": pending_count}
    )

# Add these routes after your existing routes
@routes.route("/admin/leave-requests/approve-all", methods=["POST"])
@role_required("admin")
def approve_all_leaves():
    try:
        # Get all pending leave requests
        pending_leaves = LeaveRequest.query.filter_by(status='pending').all()
        
        # Approve all pending leaves
        for leave in pending_leaves:
            leave.status = 'approved'
        
        db.session.commit()
        flash('All pending leave requests have been approved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving leave requests.', 'error')
    
    return redirect(url_for('routes.admin_leave_requests'))

# In routes.py, update the approve_leave and reject_leave functions
@routes.route("/admin/leave-requests/approve/<int:leave_id>", methods=["POST"])
@role_required("admin")
def approve_leave(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    if leave.status == 'pending':
        leave.status = 'approved'
        db.session.commit()
        flash('Leave request approved successfully!', 'success')
    else:
        flash('This leave request has already been processed.', 'warning')
    return redirect(url_for('routes.admin_leave_requests'))

@routes.route("/admin/leave-requests/reject/<int:leave_id>", methods=["POST"])
@role_required("admin")
def reject_leave(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    if leave.status == 'pending':
        leave.status = 'rejected'
        db.session.commit()
        flash('Leave request has been rejected.', 'info')
    else:
        flash('This leave request has already been processed.', 'warning')
    return redirect(url_for('routes.admin_leave_requests'))

@routes.route("/api/leave-requests/pending/count")
@role_required("admin")
def pending_leave_requests_count():
    count = LeaveRequest.query.filter_by(status='pending').count()
    return jsonify({"count": count})
# =================== ADMIN EXPORT CSV =====================
@routes.route("/admin/export_csv")
@login_required
@role_required("admin")
def export_csv():
    # Join with User and Vehicle tables to get the required data
    collections = DailyCollection.query.\
        outerjoin(User, DailyCollection.driver_id == User.id).\
        outerjoin(Vehicle, User.id == Vehicle.driver_id).\
        all()

    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Driver", "Trips", "Amount", "Vehicle", "Date"])

    for c in collections:
        # Get the first vehicle if driver has any, otherwise None
        vehicle_plate = c.driver.assigned_vehicles[0].plate_number if c.driver and c.driver.assigned_vehicles else "N/A"
        
        writer.writerow([
            c.driver.name if c.driver else "N/A",
            c.trips,
            c.amount,
            vehicle_plate,
            c.date.strftime('%Y-%m-%d') if c.date else "N/A"
        ])

    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=finance_report.csv"}
    )

@routes.route("/admin/finance", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_finance():
    today = date.today()

    # ----- Handle edit/add submissions (POST from modals) -----
    if request.method == "POST":
        # --- Collection ---
        if "collection_id" in request.form:
            col_id = request.form.get("collection_id")
            date_val = request.form.get("date")
            driver_id = request.form.get("driver_id")
            vehicle_id = request.form.get("vehicle_id")
            trips = request.form.get("trips")
            amount = request.form.get("amount")

            if col_id:
                collection = DailyCollection.query.get(col_id)
                if collection:
                    collection.date = date.fromisoformat(date_val)
                    collection.driver_id = driver_id
                    collection.vehicle_id = vehicle_id
                    collection.trips = int(trips)
                    collection.amount = float(amount)
            else:
                collection = DailyCollection(
                    date=date.fromisoformat(date_val),
                    driver_id=driver_id,
                    vehicle_id=vehicle_id,
                    trips=int(trips),
                    amount=float(amount),
                    recorded_by=current_user.id
                )
                db.session.add(collection)

            db.session.commit()
            flash("Collection saved successfully.", "success")
            return redirect(url_for("routes.admin_finance"))

        # --- Expense ---
        if "expense_id" in request.form:
            exp_id = request.form.get("expense_id")
            date_val = request.form.get("date")
            category = request.form.get("category")
            description = request.form.get("description")
            vehicle_id = request.form.get("vehicle_id")
            amount = request.form.get("amount")

            # Handle receipt file
            receipt_file = request.files.get("receipt")
            filename = None
            if receipt_file and receipt_file.filename:
                from werkzeug.utils import secure_filename
                filename = secure_filename(receipt_file.filename)
                receipt_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                receipt_file.save(receipt_path)

            if exp_id:
                expense = Expense.query.get(exp_id)
                if expense:
                    expense.date = date.fromisoformat(date_val)
                    expense.category = category
                    expense.description = description
                    expense.vehicle_id = vehicle_id if vehicle_id else None
                    expense.amount = float(amount)
                    if filename:
                        expense.receipt_number = filename
            else:
                expense = Expense(
                    date=date.fromisoformat(date_val),
                    category=category,
                    description=description,
                    vehicle_id=vehicle_id if vehicle_id else None,
                    amount=float(amount),
                    recorded_by=current_user.id,
                    receipt_number=filename
                )
                db.session.add(expense)

            db.session.commit()
            flash("Expense saved successfully.", "success")
            return redirect(url_for("routes.admin_finance"))

    # ----- Date ranges -----
    first_day_current_month = today.replace(day=1)
    last_day_current_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    first_day_prev_month = (first_day_current_month - timedelta(days=1)).replace(day=1)
    last_day_prev_month = first_day_current_month - timedelta(days=1)

    # ----- Current and previous month totals -----
    current_month_collections = db.session.query(func.coalesce(func.sum(DailyCollection.amount), 0)).filter(
        DailyCollection.date.between(first_day_current_month, last_day_current_month)
    ).scalar() or 0

    current_month_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.date.between(first_day_current_month, last_day_current_month)
    ).scalar() or 0

    prev_month_collections = db.session.query(func.coalesce(func.sum(DailyCollection.amount), 0)).filter(
        DailyCollection.date.between(first_day_prev_month, last_day_prev_month)
    ).scalar() or 0

    prev_month_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.date.between(first_day_prev_month, last_day_prev_month)
    ).scalar() or 0

    current_profit = current_month_collections - current_month_expenses
    prev_profit = prev_month_collections - prev_month_expenses
    revenue_change = ((current_month_collections - prev_month_collections) / prev_month_collections * 100) if prev_month_collections > 0 else 0
    expense_change = ((current_month_expenses - prev_month_expenses) / prev_month_expenses * 100) if prev_month_expenses > 0 else 0
    profit_change = ((current_profit - prev_profit) / prev_profit * 100) if prev_profit != 0 else 0

    # ----- Fetch all records -----
    collections = DailyCollection.query.order_by(DailyCollection.date.desc()).all()
    expenses = Expense.query.order_by(Expense.date.desc()).all()
    recent_collections = collections[:10]
    recent_expenses = expenses[:10]

    # ----- Drivers and Vehicles -----
    drivers = User.query.filter_by(role='driver').all()
    vehicles = Vehicle.query.all()

    # ----- Vehicle Expenses & Other Expenses -----
    vehicle_expenses = db.session.query(
        Vehicle.plate_number,
        func.coalesce(func.sum(Expense.amount), 0).label('total_expense')
    ).outerjoin(Expense, Expense.vehicle_id == Vehicle.id).group_by(Vehicle.id).all()

    vehicle_expenses_data = {
        'labels': [v[0] for v in vehicle_expenses],
        'data': [float(v[1]) for v in vehicle_expenses]
    }

    other_expenses = db.session.query(
        Expense.category,
        func.coalesce(func.sum(Expense.amount), 0).label('total')
    ).filter(Expense.vehicle_id.is_(None)).group_by(Expense.category).all()

    other_expenses_data = {
        'labels': [e[0] for e in other_expenses],
        'data': [float(e[1]) for e in other_expenses]
    }

    # ----- Weekly chart data -----
    chart_data = {'labels': ['1-7','8-14','15-21','22-28','29+'], 'collections': [], 'expenses': []}
    for i in range(5):
        start = first_day_current_month + timedelta(days=i*7)
        end = start + timedelta(days=6)
        if i == 4: end = last_day_current_month
        col_sum = db.session.query(func.coalesce(func.sum(DailyCollection.amount), 0)).filter(DailyCollection.date.between(start, end)).scalar() or 0
        exp_sum = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.date.between(start, end)).scalar() or 0
        chart_data['collections'].append(float(col_sum))
        chart_data['expenses'].append(float(exp_sum))

    # ----- Expense categories -----
    expense_categories = [c[0] for c in db.session.query(Expense.category).distinct().all()]

    # ----- KPIs -----
    total_collections = current_month_collections
    total_expenses = current_month_expenses
    profit_loss = total_collections - total_expenses

    return render_template(
        "admin_finance.html",
        collections=collections,
        recent_collections=recent_collections,
        expenses=expenses,
        recent_expenses=recent_expenses,
        total_collections=total_collections,
        total_expenses=total_expenses,
        profit_loss=profit_loss,
        chart_data=chart_data,
        expense_categories=expense_categories,
        drivers=drivers,
        vehicles=vehicles,
        vehicle_expenses_data=vehicle_expenses_data,
        other_expenses_data=other_expenses_data,
        start_date=first_day_current_month,
        end_date=last_day_current_month,
        revenue_change=revenue_change,
        expense_change=expense_change,
        profit_change=profit_change
    )
@routes.route("/admin/past_records", methods=["GET"])
@login_required
@role_required("admin")
def admin_past_records():
    """
    Past records page: supports filtering via query params:
      - tab: 'collections' or 'expenses' (default 'collections')
      - year (e.g. 2025), month (1-12)
      - start_date, end_date (YYYY-MM-DD)
    """
    tab = request.args.get("tab", "collections")
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # Build filter range
    filters = []
    start = None
    end = None

    if start_date and end_date:
        try:
            start = datetime.fromisoformat(start_date).date()
            end = datetime.fromisoformat(end_date).date()
        except Exception:
            start = None
            end = None

    elif year and month:
        try:
            start = dt_date(year, month, 1)
            # last day of month
            nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = nxt - timedelta(days=1)
        except Exception:
            start = None
            end = None

    elif year:
        try:
            start = dt_date(year, 1, 1)
            end = dt_date(year, 12, 31)
        except Exception:
            start = None
            end = None

    # Default to current month if nothing provided
    if not start or not end:
        today = dt_date.today() # type: ignore
        start = today.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    # Query collections and expenses within range
    collections_q = DailyCollection.query.filter(DailyCollection.date.between(start, end)).order_by(DailyCollection.date.desc())
    expenses_q = Expense.query.filter(Expense.date.between(start, end)).order_by(Expense.date.desc())

    collections = collections_q.all()
    expenses = expenses_q.all()

    # Totals
    totals = {
        "collections_total": float(sum(c.amount for c in collections)) if collections else 0.0,
        "expenses_total": float(sum(e.amount for e in expenses)) if expenses else 0.0,
        "net": float(sum(c.amount for c in collections) - sum(e.amount for e in expenses))
    }

    # For filter dropdowns / UI
    years = db.session.query(func.strftime("%Y", DailyCollection.date)).union(
        db.session.query(func.strftime("%Y", Expense.date))
    ).distinct().all()
    years = sorted({int(y[0]) for y in years if y[0] is not None}, reverse=True)

    vehicles = Vehicle.query.order_by(Vehicle.plate_number).all()

    return render_template(
        "admin_past_records.html",
        tab=tab,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        collections=collections,
        expenses=expenses,
        totals=totals,
        years=years,
        vehicles=vehicles
    )

# Save (add/edit) collection
@routes.route("/admin/past_records/save_collection", methods=["POST"])
@login_required
@role_required("admin")
def save_past_collection():
    try:
        col_id = request.form.get("collection_id")
        date_val = request.form.get("date")
        driver_id = request.form.get("driver_id") or None
        vehicle_id = request.form.get("vehicle_id") or None
        trips = request.form.get("trips") or 0
        amount = request.form.get("amount") or 0
        notes = request.form.get("notes") or None

        if not date_val:
            flash("Date is required for collection.", "danger")
            return redirect(url_for("routes.admin_past_records", tab="collections"))

        if col_id:
            col = DailyCollection.query.get(col_id)
            if not col:
                flash("Collection not found.", "danger")
                return redirect(url_for("routes.admin_past_records", tab="collections"))
            col.date = datetime.fromisoformat(date_val).date()
            col.driver_id = int(driver_id) if driver_id else None
            col.vehicle_id = int(vehicle_id) if vehicle_id else None
            col.trips = int(trips)
            col.amount = float(amount)
            col.notes = notes
        else:
            col = DailyCollection(
                date=datetime.fromisoformat(date_val).date(),
                driver_id=int(driver_id) if driver_id else None,
                vehicle_id=int(vehicle_id) if vehicle_id else None,
                trips=int(trips),
                amount=float(amount),
                notes=notes,
                recorded_by=current_user.id
            )
            db.session.add(col)

        db.session.commit()
        flash("Collection saved.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving collection: {e}", "danger")

    return redirect(url_for("routes.admin_past_records", tab="collections"))

# Save (add/edit) expense
@routes.route("/admin/past_records/save_expense", methods=["POST"])
@login_required
@role_required("admin")
def save_past_expense():
    try:
        exp_id = request.form.get("expense_id")
        date_val = request.form.get("date")
        category = request.form.get("category")
        description = request.form.get("description")
        vehicle_id = request.form.get("vehicle_id") or None
        amount = request.form.get("amount") or 0

        # receipt handling
        receipt_file = request.files.get("receipt")
        filename = None
        if receipt_file and receipt_file.filename:
            filename = secure_filename(receipt_file.filename)
            upload_dir = current_app.config.get("UPLOAD_FOLDER", os.path.join(current_app.static_folder, "uploads"))
            os.makedirs(upload_dir, exist_ok=True)
            receipt_path = os.path.join(upload_dir, filename)
            receipt_file.save(receipt_path)

        if exp_id:
            exp = Expense.query.get(exp_id)
            if not exp:
                flash("Expense not found.", "danger")
                return redirect(url_for("routes.admin_past_records", tab="expenses"))
            exp.date = datetime.fromisoformat(date_val).date()
            exp.category = category
            exp.description = description
            exp.vehicle_id = int(vehicle_id) if vehicle_id else None
            exp.amount = float(amount)
            if filename:
                exp.receipt_number = filename
        else:
            exp = Expense(
                date=datetime.fromisoformat(date_val).date(),
                category=category,
                description=description,
                vehicle_id=int(vehicle_id) if vehicle_id else None,
                amount=float(amount),
                receipt_number=filename,
                recorded_by=current_user.id
            )
            db.session.add(exp)

        db.session.commit()
        flash("Expense saved.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving expense: {e}", "danger")

    return redirect(url_for("routes.admin_past_records", tab="expenses"))

# Delete endpoints (POST to avoid side effects via GET)
@routes.route("/admin/past_records/delete_collection/<int:collection_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_past_collection(collection_id):
    try:
        col = DailyCollection.query.get_or_404(collection_id)
        db.session.delete(col)
        db.session.commit()
        flash("Collection deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting collection: {e}", "danger")
    return redirect(url_for("routes.admin_past_records", tab="collections"))

@routes.route("/admin/past_records/delete_expense/<int:expense_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_past_expense(expense_id):
    try:
        exp = Expense.query.get_or_404(expense_id)
        # optionally remove receipt file here if you want
        db.session.delete(exp)
        db.session.commit()
        flash("Expense deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting expense: {e}", "danger")
    return redirect(url_for("routes.admin_past_records", tab="expenses"))

# Export stubs (implement per your preferred library)
@routes.route('/admin/export_past_records')
@login_required
def export_past_records():
    # Fetch past records
    collections = DailyCollection.query.order_by(DailyCollection.date.desc()).all()
    expenses = Expense.query.order_by(Expense.date.desc()).all()

    # Create PDF in memory
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setTitle("Past Records")

    # Title
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, height - 50, "Past Records Report")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, height - 65, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    y = height - 90

    # --- Collections ---
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Collections")
    y -= 20
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Date")
    pdf.drawString(110, y, "Driver")
    pdf.drawString(200, y, "Vehicle")
    pdf.drawString(280, y, "Trips")
    pdf.drawString(320, y, "Amount")
    pdf.drawString(400, y, "Notes")
    y -= 15
    pdf.setFont("Helvetica", 10)

    for c in collections:
        if y < 50:  # Add new page if space is low
            pdf.showPage()
            y = height - 50
        pdf.drawString(50, y, c.date.strftime('%Y-%m-%d'))
        pdf.drawString(110, y, c.driver.name if c.driver else '-')
        pdf.drawString(200, y, c.vehicle.plate_number if c.vehicle else '-')
        pdf.drawRightString(300, y, str(c.trips))
        pdf.drawRightString(380, y, f"{c.amount:.2f}")
        pdf.drawString(400, y, c.notes or '')
        y -= 15

    y -= 20
    # --- Expenses ---
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Expenses")
    y -= 20
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Date")
    pdf.drawString(110, y, "Category")
    pdf.drawString(180, y, "Vehicle")
    pdf.drawString(250, y, "Description")
    pdf.drawString(350, y, "Amount")
    pdf.drawString(420, y, "Receipt")
    y -= 15
   
    pdf.setFont("Helvetica", 10)

    for e in expenses:
        if y < 50:
            pdf.showPage()
            y = height - 50
        pdf.drawString(50, y, e.date.strftime('%Y-%m-%d'))
        pdf.drawString(110, y, e.category)
        pdf.drawString(180, y, e.vehicle.plate_number if e.vehicle else '-')
        pdf.drawString(250, y, e.description or '')
        pdf.drawRightString(400, y, f"{e.amount:.2f}")
        pdf.drawString(420, y, e.receipt_number or '')
        
        y -= 15

    pdf.save()
    buffer.seek(0)

    filename = f"past_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')
@routes.route("/admin/finance/delete_expense/<int:expense_id>", methods=["GET"])
@login_required
@role_required("admin")
def delete_expense_route(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted successfully.", "success")
    return redirect(url_for("routes.admin_finance"))

# ----- Delete Collection -----
@routes.route("/admin/finance/delete_collection/<int:collection_id>", methods=["GET"])
@login_required
@role_required("admin")
def delete_collection_route(collection_id):
    collection = DailyCollection.query.get_or_404(collection_id)
    db.session.delete(collection)
    db.session.commit()
    flash("Collection deleted successfully.", "success")
    return redirect(url_for("routes.admin_finance"))



@routes.route("/admin/finance/download_pdf")
@login_required
@role_required("admin")
def download_finance_pdf():
    # Get date ranges for the current month
    today = date.today()
    first_day_current_month = today.replace(day=1)
    last_day_current_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    
    # Get collections and expenses for the current month
    collections = db.session.query(
        DailyCollection.date,
        User.name.label("driver_name"),
        Vehicle.plate_number.label("vehicle_plate"),
        DailyCollection.amount,
        DailyCollection.trips
    ).join(
        User, User.id == DailyCollection.driver_id
    ).outerjoin(
        Vehicle, Vehicle.id == DailyCollection.vehicle_id
    ).filter(
        DailyCollection.date.between(first_day_current_month, last_day_current_month)
    ).all()

    expenses = db.session.query(
        Expense.date,
        Expense.category,
        Expense.amount,
        Expense.description,
        Vehicle.plate_number.label("vehicle_plate"),
        User.name.label("recorded_by")
    ).outerjoin(
        Vehicle, Vehicle.id == Expense.vehicle_id
    ).join(
        User, User.id == Expense.recorded_by
    ).filter(
        Expense.date.between(first_day_current_month, last_day_current_month)
    ).all()

    # Calculate totals
    total_collections = sum(c.amount for c in collections)
    total_expenses = sum(e.amount for e in expenses)
    profit_loss = total_collections - total_expenses

    # Create PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 40
    current_y = height - margin
    
    # Add title
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width/2, current_y, "Financial Report - " + today.strftime("%B %Y"))
    current_y -= 30
    
    # Add summary section
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, current_y, "Financial Summary:")
    current_y -= 20
    
    pdf.setFont("Helvetica", 10)
    current_y = _add_pdf_line(pdf, "Total Collections:", f"${total_collections:,.2f}", margin, current_y)
    current_y = _add_pdf_line(pdf, "Total Expenses:", f"${total_expenses:,.2f}", margin, current_y)
    current_y = _add_pdf_line(pdf, "Profit/Loss:", f"${profit_loss:,.2f}", margin, current_y)
    
    current_y -= 20
    
    # Add collections section
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, current_y, "Daily Collections:")
    current_y -= 20
    
    current_y = _add_pdf_section(pdf, collections, ["Date", "Driver", "Vehicle", "Trips", "Amount"], 
                               lambda c: [c.date.strftime("%Y-%m-%d"), c.driver_name or "N/A", c.vehicle_plate or "N/A", str(c.trips), f"${c.amount:,.2f}"], 
                               margin, current_y, width - 2 * margin)
    
    current_y -= 20
    
    # Add expenses section
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, current_y, "Expenses:")
    current_y -= 20
    
    current_y = _add_pdf_section(pdf, expenses, ["Date", "Category", "Description", "Vehicle", "Amount", "Recorded By"], 
                               lambda e: [e.date.strftime("%Y-%m-%d"), e.category, e.description or "-", 
                                        e.vehicle_plate or "N/A", f"${e.amount:,.2f}", e.recorded_by], 
                               margin, current_y, width - 2 * margin)
    
    pdf.save()
    buffer.seek(0)
    
    return Response(
        buffer,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=finance_report_{today.strftime('%Y%m')}.pdf"}
    )

def _add_pdf_line(pdf, label, value, x, y, value_x=300):
    pdf.drawString(x, y, label)
    pdf.drawString(value_x, y, value)
    return y - 15

def _add_pdf_section(pdf, data, headers, row_formatter, x, y, width):
    if not data:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(x, y, "No data available")
        return y - 20
    
    # Calculate column widths
    col_count = len(headers)
    col_width = width / col_count
    
    # Draw headers
    pdf.setFont("Helvetica-Bold", 10)
    for i, header in enumerate(headers):
        pdf.drawString(x + i * col_width, y, header)
    
    y -= 15
    
    # Draw rows
    pdf.setFont("Helvetica", 9)
    for item in data:
        row = row_formatter(item)
        for i, cell in enumerate(row):
            # Truncate long text to fit in cell
            cell_str = str(cell)
            if len(cell_str) > 20:
                cell_str = cell_str[:17] + "..."
            pdf.drawString(x + i * col_width, y, cell_str)
        y -= 15
        
        # Add new page if needed
        if y < 50:
            pdf.showPage()
            y = 750
    
    return y

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

# =================== FINANCE ROUTES ===================

@routes.route("/admin/finance/collection/add", methods=["POST"])
@login_required
@role_required("admin")
def add_daily_collection():
    try:
        driver_id = request.form.get('driver_id')
        vehicle_id = request.form.get('vehicle_id')
        date_str = request.form.get('date')
        amount = float(request.form.get('amount', 0))
        trips = int(request.form.get('trips', 1))
        notes = request.form.get('notes', '')
        
        collection = DailyCollection(
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            amount=amount,
            trips=trips,
            notes=notes,
            recorded_by=current_user.id
        )
        
        db.session.add(collection)
        db.session.commit()
        flash('Collection added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding collection: {str(e)}', 'danger')
    
    return redirect(url_for('routes.admin_finance'))

@routes.route("/admin/finance/collection/<int:collection_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_collection(collection_id):
    try:
        collection = DailyCollection.query.get_or_404(collection_id)
        db.session.delete(collection)
        db.session.commit()
        flash('Collection deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting collection', 'danger')
    
    return redirect(url_for('routes.admin_finance'))

@routes.route("/admin/finance/expense/add", methods=["POST"])
@login_required
@role_required("admin")
def add_expense():
    try:
        date_str = request.form.get('date')
        category = request.form.get('category')
        amount = float(request.form.get('amount', 0))
        description = request.form.get('description', '')
        receipt_number = request.form.get('receipt_number', '')
        vehicle_id = request.form.get('vehicle_id')
        
        expense = Expense(
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            category=category,
            amount=amount,
            description=description,
            receipt_number=receipt_number if receipt_number else None,
            vehicle_id=vehicle_id if vehicle_id else None,
            recorded_by=current_user.id
        )
        
        db.session.add(expense)
        db.session.commit()
        flash('Expense added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding expense: {str(e)}', 'danger')
    
    return redirect(url_for('routes.admin_finance'))

@routes.route("/admin/finance/expense/<int:expense_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_expense(expense_id):
    try:
        expense = Expense.query.get_or_404(expense_id)
        db.session.delete(expense)
        db.session.commit()
        flash('Expense deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting expense', 'danger')
    
    return redirect(url_for('routes.admin_finance'))

@routes.route("/admin/finance/export_report")
@role_required(role="admin")
def export_finance_report():
    # Get financial data with more details
    collections = (
        db.session.query(
            DailyCollection.date,
            User.name.label("driver_name"),
            Vehicle.plate_number.label("vehicle_plate"),
            DailyCollection.amount
        )
        .join(User, User.id == DailyCollection.driver_id)
        .join(Vehicle, Vehicle.driver_id == User.id)
        .order_by(DailyCollection.date.desc())
        .all()
    )
    
    # Calculate totals and statistics
    total_revenue = sum(c.amount for c in collections)
    
    # Calculate monthly expenses (maintenance + other expenses)
    if collections:
        # Get the month and year from the first collection
        report_month = collections[0].date.replace(day=1)
        next_month = (report_month + timedelta(days=32)).replace(day=1)
        
        # Get maintenance costs for the same month
        maintenance_costs = db.session.query(
            func.sum(Maintenance.actual_cost)
        ).filter(
            Maintenance.date_reported >= report_month,
            Maintenance.date_reported < next_month
        ).scalar() or 0.0
        
        # Get other expenses for the month (you can add more expense types as needed)
        # For now, we'll just use maintenance costs
        total_expenses = float(maintenance_costs)
    else:
        total_expenses = 0.0
        
    profit = total_revenue - total_expenses
    
    # Calculate vehicle performance
    from collections import defaultdict
    vehicle_totals = defaultdict(float)
    driver_totals = defaultdict(float)
    monthly_totals = defaultdict(float)
    
    for c in collections:
        vehicle_key = c.vehicle_plate
        vehicle_totals[vehicle_key] += c.amount
        driver_totals[c.driver_name] += c.amount
        month_year = c.date.strftime('%Y-%m')
        monthly_totals[month_year] += c.amount
    
    # Sort and get top performers
    top_vehicles = sorted(vehicle_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    top_drivers = sorted(driver_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Create PDF with multiple pages
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                          rightMargin=72, leftMargin=72,
                          topMargin=72, bottomMargin=72)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', 
                               parent=styles['Title'],
                               fontSize=24,
                               spaceAfter=30)
                               
    heading1_style = ParagraphStyle('Heading1',
                                  parent=styles['Heading1'],
                                  fontSize=18,
                                  spaceAfter=12)
                                  
    heading2_style = ParagraphStyle('Heading2',
                                   parent=styles['Heading2'],
                                   fontSize=14,
                                   spaceAfter=6)
    
    normal_style = styles['Normal']
    
    # Function to create a page break
    def page_break():
        return PageBreak()
    
    # Create story (content)
    story = []
    
    # Cover Page
    logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=200, height=100)
        logo.hAlign = 'CENTER'
        story.append(logo)
    
    story.append(Spacer(1, 50))
    story.append(Paragraph("FINANCIAL PERFORMANCE REPORT", title_style))
    story.append(Paragraph("Comprehensive Analysis Report", styles['Title']))
    story.append(Spacer(1, 30))
    story.append(Paragraph(f"Generated on: {date.today().strftime('%B %d, %Y')}", styles['Normal']))
    story.append(Paragraph("MSWAKI TRANSPORT SERVICES", styles['Normal']))
    story.append(page_break())
    
    # Table of Contents
    story.append(Paragraph("Table of Contents", heading1_style))
    story.append(Spacer(1, 20))
    
    toc = [
        ("1. Executive Summary", 1),
        ("2. Financial Overview", 1),
        ("3. Top Performers", 1),
        ("  3.1 Top Vehicles", 2),
        ("  3.2 Top Drivers", 2),
        ("4. Monthly Performance", 1),
        ("5. Detailed Collections", 1)
    ]
    
    for item, level in toc:
        if level == 1:
            story.append(Paragraph(f"<b>{item}</b>", styles['Normal']))
        else:
            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{item}", styles['Normal']))
    
    story.append(page_break())
    
    # 1. Executive Summary
    story.append(Paragraph("1. Executive Summary", heading1_style))
    story.append(Spacer(1, 12))
    
    # Summary statistics
    stats_data = [
        ["Total Revenue", f"KES {total_revenue:,.2f}"],
        ["Total Expenses", f"KES {total_expenses:,.2f}"],
        ["Net Profit", f"<b>KES {profit:,.2f}</b>"],
        ["Total Collections", len(collections)],
        ["Top Vehicle", f"{top_vehicles[0][0]} (KES {top_vehicles[0][1]:,.2f})" if top_vehicles else "N/A"],
        ["Top Driver", f"{top_drivers[0][0]} (KES {top_drivers[0][1]:,.2f})" if top_drivers else "N/A"]
    ]
    
    stats_table = Table(stats_data, colWidths=[200, 200])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    story.append(stats_table)
    story.append(Spacer(1, 20))
    
    # 2. Financial Overview
    story.append(Paragraph("2. Financial Overview", heading1_style))
    story.append(Spacer(1, 12))
    
    # Add a simple bar chart (as a table for simplicity)
    story.append(Paragraph("Revenue vs Expenses", heading2_style))
    
    # 3. Top Performers
    story.append(page_break())
    story.append(Paragraph("3. Top Performers", heading1_style))
    
    # 3.1 Top Vehicles
    story.append(Paragraph("3.1 Top Performing Vehicles", heading2_style))
    
    if top_vehicles:
        vehicle_data = [["Rank", "Vehicle", "Total Revenue (KES)"]]
        for i, (vehicle, amount) in enumerate(top_vehicles, 1):
            vehicle_data.append([str(i), vehicle, f"{amount:,.2f}"])
        
        vehicle_table = Table(vehicle_data, colWidths=[50, 300, 150])
        vehicle_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ]))
        story.append(vehicle_table)
    else:
        story.append(Paragraph("No vehicle data available.", styles['Normal']))
    
    story.append(Spacer(1, 20))
    
    # 3.2 Top Drivers
    story.append(Paragraph("3.2 Top Performing Drivers", heading2_style))
    
    if top_drivers:
        driver_data = [["Rank", "Driver", "Total Collections (KES)"]]
        for i, (driver, amount) in enumerate(top_drivers, 1):
            driver_data.append([str(i), driver, f"{amount:,.2f}"])
        
        driver_table = Table(driver_data, colWidths=[50, 300, 150])
        driver_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ecc71')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ]))
        story.append(driver_table)
    else:
        story.append(Paragraph("No driver data available.", styles['Normal']))
    
    # 4. Monthly Performance
    story.append(page_break())
    story.append(Paragraph("4. Monthly Performance", heading1_style))
    
    if monthly_totals:
        monthly_data = [["Month", "Total Revenue (KES)", "% of Total"]]
        for month, amount in sorted(monthly_totals.items(), reverse=True):
            percent = (amount / total_revenue * 100) if total_revenue > 0 else 0
            monthly_data.append([
                month,
                f"{amount:,.2f}",
                f"{percent:.1f}%"
            ])
        
        monthly_table = Table(monthly_data, colWidths=[150, 150, 100])
        monthly_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9b59b6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (1, 1), (2, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ]))
        story.append(monthly_table)
    else:
        story.append(Paragraph("No monthly data available.", styles['Normal']))
    
    # 5. Detailed Collections
    story.append(page_break())
    story.append(Paragraph("5. Detailed Collections", heading1_style))
    story.append(Spacer(1, 12))
    
    if collections:
        # Group collections by month
        from itertools import groupby
        from operator import itemgetter
        
        # Sort by date
        sorted_collections = sorted([{
            'date': c.date,
            'driver': c.driver_name,
            'vehicle': c.vehicle_plate,
            'amount': c.amount,
            'month_year': c.date.strftime('%B %Y')
        } for c in collections], key=itemgetter('month_year'), reverse=True)
        
        # Group by month
        for month, month_group in groupby(sorted_collections, key=itemgetter('month_year')):
            month_collections = list(month_group)
            story.append(Paragraph(f"{month}", heading2_style))
            
            # Create table for this month
            month_data = [["Date", "Driver", "Vehicle", "Amount (KES)"]]
            for c in month_collections:
                month_data.append([
                    c['date'].strftime('%Y-%m-%d'),
                    c['driver'],
                    c['vehicle'],
                    f"{c['amount']:,.2f}"
                ])
            
            # Add total for the month
            month_total = sum(c['amount'] for c in month_collections)
            month_data.append(["", "", "<b>Monthly Total:</b>", f"<b>{month_total:,.2f}</b>"])
            
            month_table = Table(month_data, colWidths=[80, 150, 150, 100])
            month_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -2), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -2), colors.black),
                ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f5f5f5')),
                ('ALIGN', (0, -1), (-2, -1), 'RIGHT'),
            ]))
            
            story.append(month_table)
            story.append(Spacer(1, 20))
    else:
        story.append(Paragraph("No collection records found.", styles['Normal']))
    
    # Add footer with page numbers
    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(7.5*inch, 0.4*inch, text)
        canvas.drawString(0.75*inch, 0.4*inch, "MSWAKI Transport Services - Confidential")
        canvas.restoreState()
    
    # Build the document with the page number function
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    
    # Prepare the response
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=mswaki_finance_report.pdf"
    
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

def vehicle_to_dict(vehicle):
    """Convert Vehicle object to a dictionary for JSON serialization."""
    if not vehicle:
        return None
    
    return {
        'id': vehicle.id,
        'plate_number': vehicle.plate_number,
        'make': vehicle.make,
        'model': vehicle.model,
        'year': vehicle.year,
        'color': vehicle.color,
        'capacity': vehicle.capacity,
        'status': vehicle.status,
        'insurance_number': vehicle.insurance_number,
        'insurance_expiry': vehicle.insurance_expiry.isoformat() if vehicle.insurance_expiry else None,
        'registration_number': vehicle.registration_number,
        'registration_expiry': vehicle.registration_expiry.isoformat() if vehicle.registration_expiry else None,
        'odometer_reading': vehicle.odometer_reading,
        'fuel_type': vehicle.fuel_type,
        'transmission': vehicle.transmission,
        'notes': vehicle.notes,
        'driver_id': vehicle.driver_id,
        'driver_name': vehicle.driver.name if vehicle.driver else None
    }

# -------------------
# ADMIN DRIVERS PAGE
# -------------------

@routes.route('/admin/drivers')
@role_required("admin")
def admin_drivers():
    # Active and past drivers
    drivers = User.query.filter_by(role='driver', status='active').all()
    past_drivers = User.query.filter_by(role='driver', status='inactive').all()
    
    # Vehicles available for assignment
    vehicles = Vehicle.query.filter_by(status='active').all()

    return render_template(
        'admin_drivers.html',
        drivers=drivers,
        past_drivers=past_drivers,
        vehicles=vehicles
    )


# -------------------
# ADD DRIVER
# -------------------
@routes.route('/admin/add_driver', methods=['POST'])
@role_required("admin")
def add_driver():
    try:
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        vehicle_id = request.form.get('vehicle_id')

        # Validation
        if not name or not email or not password:
            flash("Name, email, and password are required.", "danger")
            return redirect(url_for('routes.admin_drivers'))

        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash("Invalid email format.", "danger")
            return redirect(url_for('routes.admin_drivers'))

        if User.query.filter_by(email=email).first():
            flash("User with this email already exists.", "danger")
            return redirect(url_for('routes.admin_drivers'))

        # Create driver
        new_driver = User(name=name, email=email, password=password, role='driver', status='active')
        db.session.add(new_driver)
        db.session.commit()

        # Assign vehicle if provided
        if vehicle_id and vehicle_id.isdigit():
            vehicle = Vehicle.query.get(int(vehicle_id))
            if vehicle:
                vehicle.driver_id = new_driver.id
                db.session.commit()

        flash("Driver added successfully!", "success")
        return redirect(url_for('routes.admin_drivers'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error adding driver: {str(e)}", "danger")
        return redirect(url_for('routes.admin_drivers'))


# -------------------
# DELETE DRIVER (Soft Delete)
# -------------------
@routes.route('/admin/driver/delete/<int:driver_id>', methods=['POST'])
@role_required("admin")
def delete_driver(driver_id):
    driver = User.query.get_or_404(driver_id)
    
    # Mark as past
    driver.status = 'inactive'

    # Unassign vehicles assigned to this driver
    vehicles = Vehicle.query.filter_by(driver_id=driver.id).all()
    for v in vehicles:
        v.driver_id = None

    db.session.commit()
    flash(f"Driver {driver.name} has been moved to Past Drivers.", "success")
    return redirect(url_for('routes.admin_drivers'))


# -------------------
# ADMIN VEHICLES PAGE
# -------------------
@routes.route('/admin/vehicles')
@role_required("admin")
def admin_vehicles():
    vehicles = Vehicle.query.filter_by(status='active').all()
    past_vehicles = Vehicle.query.filter_by(status='inactive').all()
    
    # Drivers for assignment
    drivers = User.query.filter_by(role='driver', status='active').all()

    # Vehicle status counts
    status_counts = {
        "active": Vehicle.query.filter_by(status='active').count(),
        "inactive": Vehicle.query.filter_by(status='inactive').count()
    }

    return render_template(
        'admin_vehicles.html',
        vehicles=vehicles,
        past_vehicles=past_vehicles,
        drivers=drivers,
        status_counts=status_counts
    )


# -------------------
# ADD VEHICLE
# -------------------
@routes.route('/admin/add_vehicle', methods=['POST'])
@role_required("admin")
def add_vehicle():
    try:
        plate_number = request.form.get('plate_number')
        make = request.form.get('make')
        model = request.form.get('model')
        year = request.form.get('year')
        driver_id = request.form.get('driver_id')
        color = request.form.get('color') or None
        capacity = request.form.get('capacity')
        capacity = int(capacity) if capacity else 0
        insurance_number = request.form.get('insurance_number') or None
        insurance_expiry = request.form.get('insurance_expiry') or None
        registration_number = request.form.get('registration_number') or None
        registration_expiry = request.form.get('registration_expiry') or None
        last_maintenance = request.form.get('last_maintenance') or None
        next_maintenance = request.form.get('next_maintenance') or None
        odometer_reading = request.form.get('odometer_reading')
        odometer_reading = int(odometer_reading) if odometer_reading else 0
        fuel_type = request.form.get('fuel_type') or 'Petrol'
        transmission = request.form.get('transmission') or 'Automatic'
        notes = request.form.get('notes') or None

        # Validate required fields
        if not plate_number or not make or not model or not year:
            flash("Plate number, make, model, and year are required.", "danger")
            return redirect(url_for('routes.admin_vehicles'))

        year = int(year)

        # Check for duplicate plate
        if Vehicle.query.filter(db.func.lower(Vehicle.plate_number) == plate_number.lower()).first():
            flash("A vehicle with this plate number already exists.", "danger")
            return redirect(url_for('routes.admin_vehicles'))

        vehicle = Vehicle(
            plate_number=plate_number.upper(),
            make=make,
            model=model,
            year=year,
            driver_id=int(driver_id) if driver_id else None,
            status='active',
            color=color,
            capacity=capacity,
            insurance_number=insurance_number,
            insurance_expiry=insurance_expiry,
            registration_number=registration_number,
            registration_expiry=registration_expiry,
            last_maintenance=last_maintenance,
            next_maintenance=next_maintenance,
            odometer_reading=odometer_reading,
            fuel_type=fuel_type,
            transmission=transmission,
            notes=notes
        )

        db.session.add(vehicle)
        db.session.commit()
        flash("Vehicle added successfully!", "success")
        return redirect(url_for('routes.admin_vehicles'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error adding vehicle: {str(e)}", "danger")
        return redirect(url_for('routes.admin_vehicles'))


# -------------------
# DELETE VEHICLE (Soft Delete)
# -------------------
@routes.route('/admin/vehicle/delete/<int:vehicle_id>', methods=['POST'])
@role_required("admin")
def delete_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    vehicle.status = 'inactive'  # move to past vehicles
    vehicle.driver_id = None      # unassign driver
    db.session.commit()
    flash(f"Vehicle {vehicle.plate_number} has been moved to Past Vehicles.", "success")
    return redirect(url_for('routes.admin_vehicles'))




# -------------------
# UPDATE VEHICLE
# -------------------

@routes.route('/admin/update_vehicle', methods=['POST'])
@role_required("admin")
def update_vehicle():
    try:
        vehicle_id = request.form.get('vehicle_id')
        if not vehicle_id:
            flash("Vehicle ID is required", "danger")
            return redirect(url_for('routes.admin_vehicles'))
            
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            flash("Vehicle not found", "danger")
            return redirect(url_for('routes.admin_vehicles'))
            
        # Get the current driver ID before any updates
        current_driver_id = vehicle.driver_id
        
        # Update vehicle fields
        vehicle.plate_number = request.form.get('plate_number', vehicle.plate_number).upper().strip()
        vehicle.make = request.form.get('make', vehicle.make).strip()
        vehicle.model = request.form.get('model', vehicle.model).strip()
        vehicle.year = int(request.form.get('year', vehicle.year))
        vehicle.color = request.form.get('color', vehicle.color or '').strip()
        vehicle.capacity = int(request.form.get('capacity', vehicle.capacity))
        
        # Handle driver assignment and status
        driver_id = request.form.get('driver_id')
        driver_id = int(driver_id) if driver_id and driver_id != 'None' else None
        
        # Get the driver object if a driver is being assigned
        driver = User.query.get(driver_id) if driver_id else None
        
        # If driver is being assigned
        if driver and driver.id != current_driver_id:
            # Remove vehicle from current driver if any
            if current_driver_id:
                current_driver = User.query.get(current_driver_id)
                if current_driver and vehicle in current_driver.vehicles:
                    current_driver.vehicles.remove(vehicle)
            
            # Add vehicle to new driver
            driver.vehicles.append(vehicle)
            vehicle.driver_id = driver.id
            
            # If vehicle was unassigned and now has a driver, set status to available
            if current_driver_id is None:
                vehicle.status = 'available'
        # If driver is being unassigned
        elif not driver_id and current_driver_id:
            current_driver = User.query.get(current_driver_id)
            if current_driver and vehicle in current_driver.vehicles:
                current_driver.vehicles.remove(vehicle)
            vehicle.driver_id = None
            vehicle.status = 'unassigned'
        
        # Update other fields
        vehicle.status = request.form.get('status', vehicle.status)
        vehicle.insurance_number = request.form.get('insurance_number', vehicle.insurance_number or '').strip()
        vehicle.registration_number = request.form.get('registration_number', vehicle.registration_number or '').strip()
        vehicle.fuel_type = request.form.get('fuel_type', vehicle.fuel_type)
        vehicle.transmission = request.form.get('transmission', vehicle.transmission)
        vehicle.notes = request.form.get('notes', vehicle.notes or '').strip()
        
        # Handle date fields
        def parse_date(date_str, current_date):
            if not date_str:
                return current_date
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return current_date
                
        vehicle.insurance_expiry = parse_date(
            request.form.get('insurance_expiry'), 
            vehicle.insurance_expiry
        )
        vehicle.registration_expiry = parse_date(
            request.form.get('registration_expiry'),
            vehicle.registration_expiry
        )
        
        # Handle odometer reading
        try:
            vehicle.odometer_reading = int(request.form.get('odometer_reading', vehicle.odometer_reading or 0))
        except (ValueError, TypeError):
            vehicle.odometer_reading = 0
        
        db.session.commit()
        flash(f"Vehicle {vehicle.plate_number} updated successfully!", "success")
        return redirect(url_for('routes.admin_vehicles'))
        
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while updating the vehicle: {str(e)}", "danger")
        return redirect(url_for('routes.admin_vehicles'))
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
# API ENDPOINTS
# -------------------

@routes.route('/api/vehicles/<int:vehicle_id>')
@login_required
@role_required('admin')
def get_vehicle(vehicle_id):
    """API endpoint to get vehicle details by ID"""
    try:
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        
        # Get maintenance history for the vehicle
        maintenance_history = Maintenance.query.filter_by(vehicle_id=vehicle_id)\
            .order_by(Maintenance.date_reported.desc())\
            .all()
            
        # Convert vehicle to dictionary
        vehicle_data = {
            'id': vehicle.id,
            'plate_number': vehicle.plate_number,
            'make': vehicle.make,
            'model': vehicle.model,
            'year': vehicle.year,
            'color': vehicle.color,
            'capacity': vehicle.capacity,
            'status': vehicle.status,
            'registration_number': vehicle.registration_number,
            'fuel_type': vehicle.fuel_type,
            'transmission': vehicle.transmission,
            'odometer_reading': vehicle.odometer_reading,
            'insurance_number': vehicle.insurance_number,
            'insurance_expiry': vehicle.insurance_expiry.isoformat() if vehicle.insurance_expiry else None,
            'registration_expiry': vehicle.registration_expiry.isoformat() if vehicle.registration_expiry else None,
            'notes': vehicle.notes,
            'maintenance_history': [{
                'id': m.id,
                'issue_type': m.issue_type,
                'description': m.description,
                'status': m.status,
                'date_reported': m.date_reported.isoformat(),
                'date_completed': m.date_completed.isoformat() if m.date_completed else None,
                'cost': float(m.cost) if m.cost else None,
                'notes': m.notes
            } for m in maintenance_history]
        }
        
        # Add driver info if assigned
        if vehicle.driver:
            vehicle_data['driver'] = {
                'id': vehicle.driver.id,
                'name': vehicle.driver.name,
                'phone': vehicle.driver.phone,
                'email': vehicle.driver.email
            }
            
        return jsonify(vehicle_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes.route('/api/drivers/<int:driver_id>')
@login_required
@role_required('admin')
def get_driver(driver_id):
    """API endpoint to get driver details by ID"""
    try:
        driver = User.query.filter_by(id=driver_id, role='driver').first_or_404()
        
        # Get driver's vehicles
        vehicles = Vehicle.query.filter_by(driver_id=driver_id).all()
        
        # Get driver's bookings for trip count
        total_trips = Booking.query.filter_by(driver_id=driver_id).count()
        
        # Calculate average rating (assuming there's a rating system)
        # This is a placeholder - adjust based on your actual rating system
        avg_rating = 4.5  # Default value
        
        # Convert driver to dictionary
        driver_data = {
            'id': driver.id,
            'name': driver.name,
            'email': driver.email,
            'phone': driver.phone,
            'license_number': driver.license_number,
            'license_expiry': driver.license_expiry.isoformat() if driver.license_expiry else None,
            'status': driver.status,
            'total_trips': total_trips,
            'rating': avg_rating,
            'vehicles': [{
                'id': v.id,
                'make': v.make,
                'model': v.model,
                'plate_number': v.plate_number,
                'status': v.status
            } for v in vehicles]
        }
        
        return jsonify(driver_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@routes.route("/admin/maintenance/complete/<int:maintenance_id>", methods=["POST"])
@login_required
@role_required("admin")
def complete_maintenance(maintenance_id):
    maintenance = Maintenance.query.get_or_404(maintenance_id)
    if maintenance.status == "Completed":
        flash("This maintenance is already completed.", "info")
        return redirect(url_for("routes.admin_maintenance"))

    try:
        actual_cost = float(request.form.get("actual_cost", 0))
        if actual_cost < 0:
            raise ValueError("Cost cannot be negative")
            
        maintenance.status = "Completed"
        maintenance.actual_cost = actual_cost
        maintenance.date_completed = datetime.utcnow()

        # Update vehicle status
        vehicle = Vehicle.query.get(maintenance.vehicle_id)
        if vehicle:
            vehicle.status = "available"  # Make sure this matches your Vehicle model's status values

        db.session.commit()
        flash("Maintenance marked as completed successfully.", "success")
        
    except ValueError as e:
        db.session.rollback()
        flash(f"Error updating maintenance: {str(e)}", "error")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred while updating the maintenance record.", "error")
        app.logger.error(f"Error completing maintenance: {str(e)}")
        
    return redirect(url_for("routes.admin_maintenance"))
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
@routes.route('/admin/bookings')
@login_required
def admin_bookings():
    bookings = Booking.query.order_by(Booking.id.desc()).all()

    # Convert bookings to a JSON-serializable format
    bookings_data = []
    for b in bookings:
        bookings_data.append({
            "id": b.id,
            "user_name": b.user.name if b.user else "N/A",
            "user_email": b.user.email if b.user and b.user.email else "",
            "seats": b.seats,
            "pickup": b.pickup,
            "destination": b.destination,
            "travel_date": b.travel_date.strftime("%Y-%m-%d") if b.travel_date else None,
            "travel_time": b.travel_time.strftime("%H:%M") if b.travel_time else None,
            "status": b.status,
            "rejection_reason": b.rejection_reason or ""
        })

    return render_template("admin_bookings.html", bookings=bookings, bookings_data=bookings_data)

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


@routes.route("/user/dashboard")
@login_required
@role_required("passenger")
def user_dashboard():
    """Passenger dashboard showing latest bookings."""
    bookings = Booking.query.filter_by(user_id=current_user.id)\
        .order_by(Booking.booking_date.desc()).limit(10).all()
    return render_template("user_dashboard.html", bookings=bookings)


@routes.route("/user/profile", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def user_profile():
    """View and update user profile."""
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


# ================================
# BOOKING ROUTES
# ================================

@routes.route('/book_vehicle', methods=['GET', 'POST'])
@login_required
def book_vehicle():
    if request.method == 'POST':
        seats = int(request.form.get('seats'))
        pickup = request.form.get('pickup')
        destination = request.form.get('destination')
        reason = request.form.get('reason')
        travel_date_str = request.form.get('travel_date')
        travel_time_str = request.form.get('travel_time')

        # Convert strings to date and time objects
        travel_date = datetime.strptime(travel_date_str, "%Y-%m-%d").date()
        travel_time = datetime.strptime(travel_time_str, "%H:%M").time()

        booking = Booking(
            user_id=current_user.id,
            seats=seats,
            pickup=pickup,
            destination=destination,
            reason=reason,
            travel_date=travel_date,
            travel_time=travel_time,
            status="Pending"
        )
        db.session.add(booking)
        db.session.commit()
        flash(f"Successfully booked {seats} seat(s).", "success")
        return redirect(url_for('routes.user_dashboard'))

    return render_template('book_vehicle.html')

@routes.route('/my_bookings')
@login_required
def my_bookings():
    # Fetch bookings for the logged-in user
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()

    # Prepare JSON-safe data for Modal UI
    bookings_data = []
    for b in bookings:
        bookings_data.append({
            "id": b.id,
            "seats": b.seats,
            "pickup": b.pickup,
            "destination": b.destination,
            "reason": b.reason or "",

            # Dates for modal display
            "travel_date": b.travel_date.strftime("%b %d, %Y") if b.travel_date else "N/A",
            "travel_time": b.travel_time.strftime("%I:%M %p") if b.travel_time else "N/A",

            # Status & rejection details
            "status": b.status,
            "rejection_reason": getattr(b, "rejection_reason", ""),

            # Booking created timestamp
            "created_at": b.created_at.strftime("%b %d, %Y %I:%M %p") if b.created_at else "N/A",

            # Allow cancel only when pending
            "can_cancel": b.status.lower() == "pending"
        })

    return render_template(
        "user_bookings.html",
        bookings=bookings,
        bookings_data=bookings_data
    )

@routes.route('/cancel-booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for('routes.my_bookings'))

    if booking.status != 'Pending':
        flash("Only pending bookings can be cancelled!", "info")
        return redirect(url_for('routes.my_bookings'))

    booking.status = "cancelled"
    db.session.commit()

    flash("Booking cancelled successfully", "success")
    return redirect(url_for('routes.my_bookings'))

# ================================
# REPORT MISBEHAVIOR
# ================================

@routes.route("/user/report_misbehavior", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def report_misbehavior():
    """Passenger submits misbehavior reports for drivers or vehicles."""
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
            date_reported=datetime.utcnow(),
            reporter_type="user"
        )
        db.session.add(report)
        db.session.commit()
        flash("Your report has been submitted successfully.", "success")
        return redirect(url_for("routes.user_dashboard"))

    drivers = User.query.filter_by(role="driver").all()
    vehicles = Vehicle.query.all()
    return render_template("report_misbehavior.html", drivers=drivers, vehicles=vehicles)


# ================================
# PUBLIC PAGES
# ================================

@routes.route('/about')
def about():
    """About page (public)."""
    return render_template('about.html')


@routes.route('/gallery')
def gallery():
    """Gallery page showing images of vehicles."""
    images = [
        "/static/images/matatu1.jpg",
        "/static/images/matatu2.jpg",
        "/static/images/matatu3.jpg",
        "/static/images/matatu4.jpg",
        "/static/images/matatu5.jpg"
    ]
    return render_template('gallery.html', images=images)


@routes.route('/contact-team', methods=["GET"])
def contact_team():
    """Public contact page showing drivers and owner info."""
    drivers = [
        {"name": "John Mwangi", "phone": "0712 345 678", "email": "john@mswaki.co.ke", "image": "/static/images/driver1.jpg"},
        {"name": "Sarah Muthoni", "phone": "0798 223 121", "email": "sarah@mswaki.co.ke", "image": "/static/images/driver2.jpg"},
        {"name": "Kamau Njoroge", "phone": "0721 998 112", "email": "kamau@mswaki.co.ke", "image": "/static/images/driver3.jpg"},
    ]

    owner = {
        "name": "Mswaki Transport Owner",
        "phone": "0700 000 000",
        "email": "owner@mswaki.co.ke",
        "image": "/static/images/owner.jpg"
    }

    return render_template('contact_team.html', drivers=drivers, owner=owner)


@routes.route('/send_message', methods=['POST'])
@login_required
def send_message():
    """Send message to team (requires login)."""
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')

    # Save to DB or send email here

    flash("Message sent successfully!", "success")
    return redirect(url_for('routes.contact_team'))
# ============================================================
# ERROR HANDLERS
# ============================================================
@routes.app_errorhandler(404)
def not_found(error):
    return render_template("errors/404.html"), 404

@routes.app_errorhandler(500)
def server_error(error):
    return render_template("errors/500.html"), 500
