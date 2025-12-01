from mswaki import create_app, db
from mswaki.models import LeaveRequest

app = create_app()

with app.app_context():
    # This will add any missing columns to existing tables
    db.create_all()
    print("Database schema updated successfully!")
    
    # Verify the changes
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    columns = [column['name'] for column in inspector.get_columns('leave_request')]
    print("Columns in leave_request table:", columns)
