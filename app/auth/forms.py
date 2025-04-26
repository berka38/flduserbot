from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
from app.models import User
from flask_babel import lazy_gettext as _l

class RegistrationForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(message=_l("This field is required.")), Length(min=3, max=64)])
    email = StringField(_l('Email'), validators=[DataRequired(message=_l("This field is required.")), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired(message=_l("This field is required.")), Length(min=6)])
    password2 = PasswordField(
        _l('Repeat Password'), validators=[DataRequired(message=_l("This field is required.")), EqualTo('password', message=_l('Passwords must match.'))])
    referral_code = StringField(_l('Referral Code (Optional)'), validators=[Optional(), Length(max=10)])
    submit = SubmitField(_l('Register'))

    # Kullanıcı adının zaten var olup olmadığını kontrol eden özel validator
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError(_l('This username is already taken.'))

    # E-postanın zaten var olup olmadığını kontrol eden özel validator
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError(_l('This email address is already in use.'))

# Giriş formu da ileride buraya eklenebilir
class LoginForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(message=_l("This field is required."))])
    password = PasswordField(_l('Password'), validators=[DataRequired(message=_l("This field is required."))])
    remember_me = BooleanField(_l('Remember Me'))
    submit = SubmitField(_l('Login')) 