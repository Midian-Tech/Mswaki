import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from jinja2 import Environment

# Global extension instance
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app():
    """Application factory for the Mswaki system."""
    app = Flask(__name__)

    # Config
    app.config['SECRET_KEY'] = 'your-secret-key'
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(base_dir, '..', 'instance', 'mswaki.db')
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --- UPLOAD_FOLDER config ---
    app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, '..', 'static', 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'routes.login'

    # User loader
    from mswaki.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Add zip filter to Jinja2 environment
    def zip_lists(a, b):
        return zip(a, b)
    
    app.jinja_env.filters['zip'] = zip_lists

    # Register blueprints
    from mswaki.routes import routes
    app.register_blueprint(routes)

    # Create DB tables
    with app.app_context():
        db.create_all()

    return app
