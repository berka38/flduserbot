from functools import wraps
from flask import abort
from flask_login import current_user

def admin_required(func):
    """Decorator to restrict access to admin users."""
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin': 
            abort(403) # Forbidden
        return func(*args, **kwargs)
    return decorated_view

def moderator_or_admin_required(func):
    """Decorator to restrict access to moderators and admin users."""
    @wraps(func)
    def decorated_view(*args, **kwargs):
        allowed_roles = ['admin', 'moderator']
        if not current_user.is_authenticated or current_user.role not in allowed_roles:
            abort(403) # Forbidden
        return func(*args, **kwargs)
    return decorated_view 