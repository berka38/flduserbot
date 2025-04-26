from flask import Blueprint

bp = Blueprint('auth', __name__, template_folder='templates')

# Route'lar app/auth/routes.py dosyasında tanımlanacak
# ve uygulama başlatıldığında otomatik olarak yüklenecek.

# Import routes at the end to avoid circular dependencies
from app.auth import routes 