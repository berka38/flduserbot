from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_bootstrap import Bootstrap4
from flask_babel import Babel, _
from config import Config
import os
from flask_login import LoginManager, current_user

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
bootstrap = Bootstrap4()
login_manager = LoginManager()
babel = Babel()

login_manager.login_view = 'auth.login'
login_manager.login_message_category = "info"

def get_locale():
    if 'language' in session:
        return session['language']
    return request.accept_languages.best_match(Config.LANGUAGES)

# --- Context Processor for Notifications --- 
# This function runs before each request and makes its return value
# available to all templates.
def inject_notifications():
    from app import models
    if current_user.is_authenticated:
        if hasattr(current_user, 'notifications'):
            unread_count = current_user.notifications.filter_by(is_read=False).count()
            return dict(unread_notifications_count=unread_count)
    return dict(unread_notifications_count=0)
# --- End Context Processor ---

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize extensions FIRST
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    bootstrap.init_app(app)
    login_manager.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    
    # Import models AFTER initializing db and other extensions
    # This is crucial to avoid circular imports
    with app.app_context():
        from app import models

    # Register context processor AFTER models are potentially available
    app.context_processor(inject_notifications)

    # Register Blueprints (they might import models)
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.bot import bp as bot_bp
    app.register_blueprint(bot_bp, url_prefix='/bot')

    # Register Admin blueprint
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @login_manager.user_loader
    def load_user(user_id):
        user = models.User.query.get(int(user_id))
        return user

    return app 