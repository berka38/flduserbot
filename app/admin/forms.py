from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, SelectField, IntegerField
from wtforms.validators import DataRequired, Optional
from flask_babel import lazy_gettext as _l

# Rol seçenekleri (daha sonra genişletilebilir)
# Değerler modeldeki stringlerle aynı olmalı
ROLES = [
    ('user', _l('User')),
    ('moderator', _l('Moderator')),
    ('premium', _l('Premium User')),
    ('admin', _l('Admin')),
    # ('moderator', _l('Moderator')),
]

class EditUserForm(FlaskForm):
    username = StringField(_l('Username'), render_kw={'readonly': True})
    email = StringField(_l('Email'), render_kw={'readonly': True})
    role = SelectField(_l('Role'), choices=ROLES, validators=[DataRequired()])
    # Field to add/remove credits. Use Optional() as it's not always required.
    credit_adjustment = IntegerField(_l('Add/Remove Credits (e.g., 100 or -50)'), default=0, validators=[Optional()])
    submit = SubmitField(_l('Save Changes')) 