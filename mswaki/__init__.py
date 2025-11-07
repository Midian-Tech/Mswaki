import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Initialize extensions (but not bound to app yet)
db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    """Application factory for the Mswaki system."""
    app = Flask(__name__)

    # -------------------------
    # 🔐 Basic Configurations
    # -------------------------
    app.config['SECRET_KEY'] = 'your-secret-key'  # Change this to an environment variable in production

    # Build absolute path to the database file in /instance/mswaki.db
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(base_dir, '..', 'instance', 'mswaki.db')
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # -------------------------
    # 🔧 Initialize Extensions
    # -------------------------
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'routes.login'  # Redirect here if user not logged in

    # -------------------------
    # 👤 User Loader (for Flask-Login)
    # -------------------------
    from mswaki.models import User  # Import here to avoid circular import

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # -------------------------
    # 🧭 Register Blueprints
    # -------------------------
    from mswaki.routes import routes
    app.register_blueprint(routes)

    # -------------------------
    # 🗃️ Create database tables (only if they don't exist)
    # -------------------------
    with app.app_context():
        db.create_all()

    # -------------------------
    # ✅ Return the configured app
    # -------------------------
    return app
