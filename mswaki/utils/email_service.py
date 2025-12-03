from flask_mail import Message
from mswaki import mail


def send_email(subject, recipients, body):
    msg = Message(subject, recipients=recipients)
    msg.body = body

    try:
        mail.send(msg)
        print(f"📧 Email sent to: {recipients}")
        return True
    except Exception as e:
        print(f"❌ Email send failed: {e}")
        return False


def send_booking_status_email(booking, user):
    if booking.status.lower() == "approved":
        subject = "Your Booking Has Been Approved 🚐"
        body = f"""
Hello {user.name},

Your booking has been approved 🎉

📍 Pickup: {booking.pickup}
🏁 Destination: {booking.destination}
📅 Date: {booking.travel_date}
⏰ Time: {booking.travel_time}

Safe travels with Mswaki Transport 🚌
        """
    else:
        subject = "Your Booking Was Rejected ❌"
        body = f"""
Hello {user.name},

Unfortunately, your booking request was rejected.

Reason: {booking.rejection_reason or "Not specified"}

You may try booking again later.
        """

    return send_email(subject, [user.email], body)


def notify_admin_new_booking(booking):
    admin_email = "mswakitransport@gmail.com"

    subject = "📩 New Booking Received"
    body = f"""
A user submitted a new booking:

👤 User: {booking.user.name}
📧 Email: {booking.user.email}

📍 Pickup: {booking.pickup}
🏁 Destination: {booking.destination}
💺 Seats: {booking.seats}

Please review it in the Admin Panel.
    """
    return send_email(subject, [admin_email], body)


def notify_admin_new_report(report):
    admin_email = "mswakitransport@gmail.com"

    subject = "⚠️ New Misbehavior Report Alert"
    body = f"""
A misconduct report was submitted:

👤 Reporter: {report.user.name}
📧 Email: {report.user.email}

📝 Message:
{report.message}

Please review it in the Admin Panel.
"""
    return send_email(subject, [admin_email], body)
