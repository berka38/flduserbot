from . import bp
from flask import render_template, session, redirect, url_for, request, flash
from config import Config
from flask_login import login_required, current_user
from app.models import Notification, AffiliateEarning, User, PythonCommand, CommandRating, CommandCategory
from app import db
from datetime import datetime
from flask_babel import _
from sqlalchemy import func, desc
import decimal
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError
from sqlalchemy.exc import IntegrityError
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter
from markupsafe import Markup
# Correctly import from bot blueprint's forms
from app.bot.forms import CommandRatingForm

@bp.route('/')
@bp.route('/index')
def index():
    return render_template('main/index.html', title='Ana Sayfa')
    # return "<h1>Ana Sayfa Çalışıyor!</h1>"

# Dil değiştirme route'u
@bp.route('/set_language/<language>')
def set_language(language):
    if language not in Config.LANGUAGES:
        # Geçersiz dil seçimi, ana sayfaya yönlendirilebilir veya hata verilebilir
        return redirect(url_for('main.index'))

    session['language'] = language
    # Kullanıcıyı önceki sayfaya geri yönlendir
    # Eğer referer bilgisi yoksa veya güvenli değilse ana sayfaya yönlendir
    referer = request.headers.get('Referer')
    if referer and url_for('main.set_language', language=language) not in referer:
        return redirect(referer)
    else:
        return redirect(url_for('main.index'))

@bp.route('/notifications')
@login_required
def notifications():
    """Displays user notifications and marks them as read."""
    
    # Get current time before query to avoid race condition
    since = datetime.utcnow() 
    
    # Fetch notifications ordered by timestamp descending
    user_notifications = current_user.notifications.order_by(Notification.timestamp.desc()).all()
    
    # Mark fetched notifications as read
    try:
        for notification in user_notifications:
            if not notification.is_read:
                notification.is_read = True
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"!!! Error marking notifications as read for user {current_user.id}: {e}")
        flash(_("Error updating notification status."), "danger")
        
    return render_template('main/notifications.html', 
                           title=_('Notifications'), 
                           notifications=user_notifications)

@bp.route('/affiliate')
@login_required
def affiliate_dashboard():
    """Displays the affiliate dashboard for the logged-in user."""
    
    # Ensure user has an affiliate code (should have been generated on register)
    if not current_user.affiliate_code:
        try:
            current_user.generate_affiliate_code()
            db.session.add(current_user)
            db.session.commit()
            print(f"--- Generated missing affiliate code {current_user.affiliate_code} for user {current_user.username} on dashboard access")
        except Exception as e:
            db.session.rollback()
            print(f"!!! Error generating missing affiliate code for user {current_user.username}: {e}")
            flash(_("Could not generate your affiliate code. Please contact support."), "danger")
            # Optionally redirect or just show dashboard without code
            
    # Get referrals and earnings
    referrals = current_user.referrals.all() # Users referred by current_user
    earnings = current_user.affiliate_earnings.order_by(AffiliateEarning.timestamp.desc()).all() # Earnings of current_user
    
    # Calculate total pending and paid earnings
    # Ensure amount is treated as Decimal for summation
    pending_sum = db.session.query(func.sum(AffiliateEarning.amount)).filter(
        AffiliateEarning.affiliate_id == current_user.id,
        AffiliateEarning.status == 'pending'
    ).scalar() or decimal.Decimal('0.00')
    
    paid_sum = db.session.query(func.sum(AffiliateEarning.amount)).filter(
        AffiliateEarning.affiliate_id == current_user.id,
        AffiliateEarning.status == 'paid'
    ).scalar() or decimal.Decimal('0.00')
        
    return render_template('main/affiliate_dashboard.html',
                           title=_('Affiliate Dashboard'),
                           referrals=referrals,
                           earnings=earnings,
                           pending_total=pending_sum,
                           paid_total=paid_sum)

# TODO: Add admin view/management for affiliate earnings (mark as paid etc.)

# TODO: Add route to clear/delete notifications?

@bp.route('/market')
@login_required
def market():
    """Displays publicly shared Python commands, optionally filtered by category."""
    page = request.args.get('page', 1, type=int)
    category_slug = request.args.get('category', None)
    
    # Base query for approved, public commands
    base_query = PythonCommand.query.filter(
        PythonCommand.status == 'approved',
        PythonCommand.is_public == True
    )
    
    selected_category = None
    # Filter by category if slug is provided
    if category_slug:
        selected_category = CommandCategory.query.filter_by(slug=category_slug).first()
        if selected_category:
            # Use the relationship to filter commands belonging to this category
            base_query = base_query.join(PythonCommand.categories).filter(CommandCategory.id == selected_category.id)
        else:
             # Category not found, maybe flash a message or just show all?
             flash(_("Category '%(slug)s' not found.", slug=category_slug), 'warning')
             # Redirect to market without category filter to avoid confusion
             return redirect(url_for('main.market'))

    # Order and paginate
    public_commands_pagination = base_query.order_by(PythonCommand.updated_at.desc()).paginate(page=page, per_page=15, error_out=False)
    
    commands = public_commands_pagination.items
    
    # Calculate average rating for each command
    for command in commands:
        # Query average rating, handle None case with 0
        avg_rating = db.session.query(func.avg(CommandRating.rating)) \
                        .filter(CommandRating.python_command_id == command.id) \
                        .scalar() or 0
        # Attach the average rating to the command object for use in the template
        command.average_rating = avg_rating 
        # Optional: Also attach number of ratings if needed in the market view
        # command.num_ratings = command.ratings.count() 
        
    # Get all categories for display
    all_categories = CommandCategory.query.order_by(CommandCategory.name).all()
    
    return render_template('main/market.html', 
                           title=_('Command Market'),
                           commands=commands,
                           pagination=public_commands_pagination,
                           categories=all_categories, # Pass all categories
                           selected_category=selected_category) # Pass selected category

@bp.route('/market/command/<int:command_id>/rate', methods=['POST'])
@login_required
def rate_command(command_id):
    """Handles the submission of a rating and comment for a command."""
    command = PythonCommand.query.get_or_404(command_id)
    
    # Ensure command is public and approved to be rated
    if not command.is_public or command.status != 'approved':
        flash(_('This command cannot be rated currently.'), 'warning')
        return redirect(url_for('main.market'))
        
    # Instantiate the form (using data from request.form because it came from a manually rendered modal)
    form = CommandRatingForm(request.form) 
    
    # Validate manually (since WTForms might not pick up request.form directly in this setup)
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()
    csrf_token_received = request.form.get('csrf_token') # Get CSRF token
    
    # Basic validation
    # CSRF check (Flask-WTF usually handles this, but let's do a basic check)
    # This might need a more robust check depending on your CSRF setup
    try:
        validate_csrf(csrf_token_received)
    except ValidationError:
         flash(_('Invalid CSRF token. Please try again.'), 'danger')
         return redirect(url_for('main.market'))

    if not rating or rating < 1 or rating > 5:
         flash(_('Invalid rating submitted. Please select a value between 1 and 5.'), 'danger')
         return redirect(url_for('main.market'))
         
    if len(comment) > 500:
        flash(_('Comment cannot exceed 500 characters.'), 'danger')
        return redirect(url_for('main.market'))

    # Check if user has already rated this command
    existing_rating = CommandRating.query.filter_by(
        python_command_id=command.id,
        user_id=current_user.id
    ).first()

    try:
        if existing_rating:
            # Update existing rating
            existing_rating.rating = rating
            existing_rating.comment = comment
            existing_rating.timestamp = datetime.utcnow()
            flash(_('Your rating for command \'%(trigger)s\' has been updated.', trigger=command.trigger), 'success')
        else:
            # Create new rating
            new_rating = CommandRating(
                python_command_id=command.id,
                user_id=current_user.id,
                rating=rating,
                comment=comment
            )
            db.session.add(new_rating)
            flash(_('Your rating for command \'%(trigger)s\' has been submitted.', trigger=command.trigger), 'success')
            
            # Optional: Award credits to the command submitter for receiving a rating?
            # submitter = command.submitter
            # if submitter and submitter.id != current_user.id: # Don't award for self-rating
            #    submitter.credits += 1 # Example: +1 credit per rating
            #    db.session.add(submitter)

        db.session.commit()

    except IntegrityError as e: # Should not happen due to check above, but good practice
        db.session.rollback()
        print(f"!!! IntegrityError rating command {command.id} by user {current_user.id}: {e}")
        flash(_('A database error occurred while submitting your rating.'), 'danger')
    except Exception as e:
        db.session.rollback()
        print(f"!!! Error rating command {command.id} by user {current_user.id}: {e}")
        flash(_('An unexpected error occurred while submitting your rating.'), 'danger')

    return redirect(url_for('main.market')) 

@bp.route('/market/command/<int:command_id>')
@login_required
def command_detail(command_id):
    """Displays the details of a specific public command."""
    command = PythonCommand.query.filter(
        PythonCommand.id == command_id,
        PythonCommand.is_public == True,
        PythonCommand.status == 'approved'
    ).first_or_404()

    # Fetch ratings/comments for this command, ordered by timestamp
    ratings = command.ratings.order_by(CommandRating.timestamp.desc()).all()
    
    # Calculate average rating
    avg_rating = db.session.query(func.avg(CommandRating.rating)).filter(CommandRating.python_command_id == command.id).scalar() or 0
    num_ratings = len(ratings)
    
    # Highlight Python code
    # formatter = HtmlFormatter(style='default', cssclass='codehilite')
    # Create formatter that includes the <style> tags
    formatter = HtmlFormatter(style='default', full=True, cssclass='codehilite') 
    pygments_css = formatter.get_style_defs()
    # Highlight just the code body without the full HTML document structure
    highlighted_code = Markup(highlight(command.code_body, PythonLexer(), HtmlFormatter(style='default', cssclass='codehilite')))

    # Form for submitting a new rating (similar to the modal)
    rating_form = CommandRatingForm() # For potential future inline form

    return render_template('main/command_detail.html',
                           title=f"Command: {command.trigger}",
                           command=command,
                           ratings=ratings,
                           avg_rating=avg_rating,
                           num_ratings=num_ratings,
                           highlighted_code=highlighted_code,
                           rating_form=rating_form, # Pass form
                           pygments_css=Markup(pygments_css) # Pass CSS to template
                           ) 