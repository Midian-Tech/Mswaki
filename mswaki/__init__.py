import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail

# Global extension instances
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()  # <-- Mail instance added

def create_app():
    """Application factory for the Mswaki system."""
    app = Flask(__name__)

    # Basic Config
    app.config['SECRET_KEY'] = 'your-secret-key'
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(base_dir, '..', 'instance', 'mswaki.db')
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Upload folder
    app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, '..', 'static', 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ---------------- Gmail SMTP Email Config ----------------
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'mswakitransport@gmail.com'
    app.config['MAIL_PASSWORD'] = 'qamvrwsfslgukjgz'  # <-- NO spaces!!
    app.config['MAIL_DEFAULT_SENDER'] = 'mswakitransport@gmail.com'
    # ---------------------------------------------------------

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'routes.login'

    # User loader
    from mswaki.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Jinja2 zip helper
    def zip_lists(a, b):
        return zip(a, b)
    app.jinja_env.filters['zip'] = zip_lists

    # Register routes
    from mswaki.routes import routes
    app.register_blueprint(routes)

    # Create DB tables if not exists
    with app.app_context():
        db.create_all()

    return app
