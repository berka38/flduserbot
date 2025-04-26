from flask import Blueprint

bp = Blueprint('main', __name__)

# Route'lar app/main/routes.py dosyasında tanımlanacak
# ve uygulama başlatıldığında otomatik olarak yüklenecek.

# Import routes at the end to avoid circular dependencies
from app.main import routes 