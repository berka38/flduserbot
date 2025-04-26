from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired
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
    submit = SubmitField(_l('Save Changes')) 