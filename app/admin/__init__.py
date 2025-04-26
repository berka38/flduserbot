from flask import Blueprint

bp = Blueprint('admin', __name__, template_folder='templates')

from . import routes # Import routes at the end 