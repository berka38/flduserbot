from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, SelectField, RadioField, TextAreaField
from wtforms.fields import SelectMultipleField
from wtforms.widgets import TextArea, ListWidget, CheckboxInput
from wtforms.validators import DataRequired, Regexp, Length, Optional, NumberRange
from app.models import TelegramAccount, CustomCommand, PythonCommand, CommandCategory
from flask_login import current_user
from wtforms import ValidationError
from flask_babel import lazy_gettext as _l

# Yanıt uzunluk limitini tanımla
RESPONSE_LENGTH_LIMIT = 50

def validate_response_length(form, field):
    """Custom validator to check response length based on user role."""
    # Check if the user is premium or admin
    is_privileged = current_user.is_authenticated and (current_user.is_premium() or current_user.is_admin())
    
    if not is_privileged and len(field.data) > RESPONSE_LENGTH_LIMIT:
        # Translate the error message directly using _
        raise ValidationError(_(
            'Response text cannot exceed %(limit)s characters for your account type. Upgrade to Premium for longer responses.',
            limit=RESPONSE_LENGTH_LIMIT
        ))

class AddBotForm(FlaskForm):
    phone_number = StringField(
        _l('Phone Number (International format, e.g., +905xxxxxxxxx)'),
        validators=[
            DataRequired(message=_l("This field is required.")),
            Regexp(r'^\+?\d{10,15}$', message=_l("Please enter a valid phone number (e.g., +90...)."))
        ]
    )
    api_id = IntegerField(_l('API ID'), validators=[DataRequired(message=_l("This field is required."))])
    api_hash = StringField(_l('API Hash'), validators=[DataRequired(message=_l("This field is required."))])
    submit = SubmitField(_l('Add Account'))

    # Kullanıcının aynı telefon numarasını tekrar eklemesini engelle
    def validate_phone_number(self, phone_number):
        # Numarayı temizleyelim (başındaki + kalabilir)
        cleaned_phone = '+' + ''.join(filter(str.isdigit, phone_number.data))
        account = TelegramAccount.query.filter_by(user_id=current_user.id, phone_number=cleaned_phone).first()
        if account:
            raise ValidationError(_l('This phone number has already been added.'))

class EnterCodeForm(FlaskForm):
    code = StringField(_l('Verification Code'), validators=[DataRequired(message=_l("This field is required."))])
    submit = SubmitField(_l('Login'))

class AddCustomCommandForm(FlaskForm):
    trigger = StringField(_l('Trigger Word/Phrase'), validators=[
        DataRequired(message=_l("This field is required.")),
        Regexp(r'^!?[\w\s]+$', message=_l("Invalid characters. Use letters, numbers, spaces, and an optional '!' at the beginning."))
        ])
    response = StringField(_l('Response Text'), widget=TextArea(), validators=[
        DataRequired(message=_l("This field is required.")),
        validate_response_length
        ])
    submit = SubmitField(_l('Add Command'))

    # account_id'yi form oluşturulurken alacağız
    def __init__(self, account_id, *args, **kwargs):
        super(AddCustomCommandForm, self).__init__(*args, **kwargs)
        self.account_id = account_id

    # Aynı hesap için aynı tetikleyicinin tekrar eklenmesini engelle
    def validate_trigger(self, trigger):
        existing_command = CustomCommand.query.filter_by(
            account_id=self.account_id,
            trigger=trigger.data
        ).first()
        if existing_command:
            raise ValidationError(_l('This trigger word is already defined for this account.'))

class EditCustomCommandForm(FlaskForm):
    # Trigger'ı gösterelim ama düzenlenemez yapalım (veya istersen düzenlenebilir yaparız?)
    trigger = StringField(_l('Trigger (Cannot be changed)'), render_kw={'readonly': True})
    response = StringField(_l('Response Text'), widget=TextArea(), validators=[
        DataRequired(message=_l("This field is required.")),
        validate_response_length
        ])
    submit = SubmitField(_l('Save Changes'))

# --- Form for Adding Python Commands ---
class AddPythonCommandForm(FlaskForm):
    trigger = StringField(_l('Trigger (e.g., !py_info)'), validators=[
        DataRequired(message=_l("This field is required.")),
        Regexp(r'^![\w\-]+$', message=_l("Trigger must start with '!' and contain only letters, numbers, underscore, or hyphen."))
        ])
    description = StringField(_l('Description'), widget=TextArea(), validators=[
        DataRequired(message=_l("This field is required.")),
        Length(max=255)
        ])
    code_body = StringField(_l('Python Code'), 
                            widget=TextArea(), 
                            render_kw={'rows': 15},
                            validators=[DataRequired(message=_l("This field is required."))]
                            )
    # Category Selection
    categories = SelectMultipleField(
        _l('Categories (Optional)'), 
        coerce=int, 
        widget=ListWidget(prefix_label=False), 
        option_widget=CheckboxInput(),
        validators=[Optional()]
        )
    submit = SubmitField(_l('Submit Command for Review'))

    # We need the account_id to check for duplicate triggers within the same account
    def __init__(self, account_id, *args, **kwargs):
        super(AddPythonCommandForm, self).__init__(*args, **kwargs)
        self.account_id = account_id
        # Populate categories dynamically
        self.categories.choices = [(c.id, c.name) for c in CommandCategory.query.order_by('name').all()]

    # Prevent duplicate triggers per account
    def validate_trigger(self, trigger):
        existing_py_command = PythonCommand.query.filter_by(
            account_id=self.account_id,
            trigger=trigger.data
        ).first()
        if existing_py_command:
            raise ValidationError(_l('This trigger is already used by another Python command for this account.'))
        
        # Optional: Check against CustomCommand triggers too?
        # from app.models import CustomCommand
        # existing_cust_command = CustomCommand.query.filter_by(...).first()
        # if existing_cust_command:
        #    raise ValidationError(_l('This trigger is already used by a simple custom command for this account.'))

# --- Form for selecting account when adding from market ---
class SelectAccountForMarketCommandForm(FlaskForm):
    # Dynamically populated dropdown for user's accounts
    account = SelectField(_l('Select Account to Add Command To'), coerce=int, validators=[DataRequired()])
    submit = SubmitField(_l('Add Command to Selected Account'))

    def __init__(self, user_accounts, *args, **kwargs):
        super(SelectAccountForMarketCommandForm, self).__init__(*args, **kwargs)
        # Populate choices for the SelectField
        # Choices should be a list of tuples: (value, label)
        self.account.choices = [(acc.id, acc.phone_number) for acc in user_accounts]
        if not user_accounts:
             # Disable submit if user has no accounts
            self.submit.render_kw = {'disabled': True}

# --- Form for Rating/Reviewing a Market Command --- 
class CommandRatingForm(FlaskForm):
    rating = RadioField(
        _l('Rating'), 
        choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')], 
        coerce=int, 
        validators=[DataRequired(message=_l("Please select a rating."))]
    )
    comment = TextAreaField(
        _l('Comment (Optional)'), 
        validators=[Optional(), Length(max=500)] # Optional comment, max 500 chars
    )
    submit = SubmitField(_l('Submit Review')) 