from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required, current_user
from . import bp
from app.decorators import admin_required, moderator_or_admin_required
from app.models import User, TelegramAccount, AffiliateEarning, PythonCommand, CustomCommand
from .forms import EditUserForm
from app import db
import subprocess
import os
from flask_babel import _ # gettext import
import decimal # Import decimal for commission amount
from datetime import datetime, timedelta
from sqlalchemy import func # Import func for count aggregation
import json # Import json for converting lists to JSON strings

# Define commission amount (can be moved to config)
DEFAULT_COMMISSION_AMOUNT = decimal.Decimal("5.00")

@bp.route('/')
@login_required
@moderator_or_admin_required
def index():
    """Admin dashboard.
       Accessible by Admins and Moderators.
    """
    # --- Query Statistics ---
    total_users = User.query.count()
    total_bots = TelegramAccount.query.count()
    running_bot_pids = current_app.config.get('RUNNING_BOTS', {}).keys()
    active_bots_count = len(running_bot_pids)
    pending_python_commands_count = PythonCommand.query.filter_by(status='pending').count()
    total_custom_commands = CustomCommand.query.count()
    total_python_commands = PythonCommand.query.count()
    
    # --- Query User Registration Trend (Last 7 Days) ---
    today = datetime.utcnow().date()
    seven_days_ago = today - timedelta(days=6)
    
    # Query users registered in the last 7 days, grouped by date
    user_reg_data = db.session.query(
        func.date(User.created_at), # Extract date part
        func.count(User.id)         # Count users per date
    ).filter(
        User.created_at >= seven_days_ago
    ).group_by(
        func.date(User.created_at)
    ).order_by(
        func.date(User.created_at)
    ).all()
    
    # Prepare data for Chart.js
    user_reg_labels = []
    user_reg_counts = []
    # Create a dictionary for quick lookup
    reg_dict = {date.strftime('%Y-%m-%d'): count for date, count in user_reg_data}
    
    # Fill data for the last 7 days, ensuring all days are present
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        user_reg_labels.append(day.strftime('%b %d')) # Format date like 'Apr 26'
        user_reg_counts.append(reg_dict.get(day_str, 0)) # Get count or 0 if no registration
        
    # --- End User Registration Trend ---
    
    return render_template('admin/index.html', 
                           title=_('Admin Panel'),
                           # Pass stats to the template
                           total_users=total_users,
                           total_bots=total_bots,
                           active_bots_count=active_bots_count,
                           pending_python_commands_count=pending_python_commands_count,
                           total_custom_commands=total_custom_commands,
                           total_python_commands=total_python_commands,
                           # Pass chart data
                           user_reg_labels=json.dumps(user_reg_labels), # Convert lists to JSON strings
                           user_reg_counts=json.dumps(user_reg_counts)
                           )

@bp.route('/users')
@login_required
@moderator_or_admin_required
def list_users():
    """List all users.
       Accessible by Admins and Moderators.
    """
    users = User.query.order_by(User.id.asc()).all()
    return render_template('admin/list_users.html', title=_('User List'), users=users)

@bp.route('/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)
    
    if user_to_delete == current_user:
        flash(_('You cannot delete yourself.'), 'danger')
        return redirect(url_for('admin.list_users'))

    username = user_to_delete.username
    running_bots = current_app.config.get('RUNNING_BOTS', {})
    accounts_to_check = list(running_bots.keys())
    
    for account_id in accounts_to_check:
        account = TelegramAccount.query.get(account_id)
        if account and account.user_id == user_to_delete.id:
            process = running_bots.get(account_id)
            if process:
                try:
                    pid = process.pid
                    process.terminate()
                    process.wait(timeout=3)
                    print(f"--- Terminated bot runner PID {pid} for deleted user {username}")
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    print(f"--- Killed bot runner PID {pid} for deleted user {username}")
                except Exception as e:
                    print(f"--- Error stopping bot PID {process.pid if process else 'N/A'} for deleted user {username}: {e}")
                finally:
                    if account_id in running_bots:
                       del running_bots[account_id]
                       
            session_path = f"instance/{user_to_delete.id}_{account_id}.session"
            session_journal_path = session_path + "-journal"
            try:
                if os.path.exists(session_path): os.remove(session_path)
                if os.path.exists(session_journal_path): os.remove(session_journal_path)
            except Exception as e:
                 print(f"--- Error deleting session files for account {account_id} of user {username}: {e}")

    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(_('User \'{username}\' deleted successfully.').format(username=username), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('Database error while deleting user: %(error)s', error=str(e)), 'danger')
        
    return redirect(url_for('admin.list_users'))

@bp.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    form = EditUserForm(obj=user_to_edit)
    original_role = user_to_edit.role # Store original role before changes

    if form.validate_on_submit():
        new_role = form.role.data
        if user_to_edit == current_user and new_role != 'admin':
             flash(_('You cannot remove your own admin privileges.'), 'danger')
        else:
            user_to_edit.role = new_role
            # --- Add Affiliate Commission Logic --- 
            try:
                # Check if role changed TO premium AND user was referred
                if new_role == 'premium' and original_role != 'premium' and user_to_edit.referred_by_id:
                    # Check if commission already paid for this referral (simple check)
                    existing_earning = AffiliateEarning.query.filter_by(
                        referred_user_id=user_to_edit.id,
                        affiliate_id=user_to_edit.referred_by_id
                    ).first()
                    
                    if not existing_earning:
                        earning = AffiliateEarning(
                            affiliate_id=user_to_edit.referred_by_id,
                            referred_user_id=user_to_edit.id,
                            amount=DEFAULT_COMMISSION_AMOUNT,
                            status='pending' # Default status
                        )
                        db.session.add(earning)
                        print(f"--- Created pending affiliate earning of {earning.amount} for user {earning.affiliate_id} from referral {earning.referred_user_id}")
                        # Optionally notify the affiliate?
                    else:
                        print(f"--- Commission already recorded for referral {user_to_edit.id} to affiliate {user_to_edit.referred_by_id}")
                        
                db.session.commit()
                flash(_('User \'{username}\' updated successfully.').format(username=user_to_edit.username), 'success')
            except Exception as e:
                db.session.rollback()
                print(f"!!! Error during user update or commission creation: {e}")
                flash(_('An error occurred while updating the user or processing commission.'), 'danger')
            # --- End Affiliate Commission Logic --- 
                
        return redirect(url_for('admin.list_users'))
    elif request.method == 'GET':
        form.username.data = user_to_edit.username
        form.email.data = user_to_edit.email
        form.role.data = user_to_edit.role
        
    return render_template(
        'admin/edit_user.html',
        title=_('Edit User \'{username}\'').format(username=user_to_edit.username),
        form=form,
        user=user_to_edit
    )

# --- Affiliate Management Routes --- 

@bp.route('/affiliate/earnings')
@login_required
@admin_required
def manage_earnings():
    """Admin view to manage affiliate earnings."""
    page = request.args.get('page', 1, type=int)
    # Query all earnings, ordered by timestamp descending, paginated
    earnings_pagination = AffiliateEarning.query.order_by(
        AffiliateEarning.timestamp.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    earnings = earnings_pagination.items
    
    return render_template('admin/manage_earnings.html',
                           title=_('Manage Affiliate Earnings'),
                           earnings=earnings,
                           pagination=earnings_pagination)

@bp.route('/earning/<int:earning_id>/update_status', methods=['POST'])
@login_required
@admin_required
def update_earning_status(earning_id):
    """Updates the status of an affiliate earning record."""
    earning = AffiliateEarning.query.get_or_404(earning_id)
    new_status = request.form.get('status')
    allowed_statuses = ['pending', 'paid', 'cancelled']
    
    if new_status in allowed_statuses:
        try:
            earning.status = new_status
            # Optionally add notes if provided (e.g., cancellation reason)
            notes = request.form.get('notes')
            if notes:
                earning.notes = notes
            elif new_status == 'cancelled' and not earning.notes:
                 earning.notes = _("Status updated by admin.") # Default note
                 
            db.session.commit()
            flash(_('Earning status updated successfully.'), 'success')
        except Exception as e:
            db.session.rollback()
            print(f"!!! Error updating earning status for ID {earning_id}: {e}")
            flash(_('Error updating earning status.'), 'danger')
    else:
        flash(_('Invalid status provided.'), 'danger')
        
    # Redirect back to the earnings management page
    # Try to redirect to the same page the request came from
    page = request.args.get('page', 1) 
    return redirect(url_for('admin.manage_earnings', page=page))

# --- End Affiliate Management --- 

# --- Python Command Review Routes --- 

@bp.route('/python_commands/review')
@login_required
@admin_required
def review_python_commands():
    """Admin view to review pending Python commands."""
    page = request.args.get('page', 1, type=int)
    # Query pending commands, ordered by creation date, paginated
    pending_commands_pagination = PythonCommand.query.filter_by(status='pending')\
        .order_by(PythonCommand.created_at.asc())\
        .paginate(page=page, per_page=10, error_out=False)
    
    commands = pending_commands_pagination.items
    
    return render_template('admin/review_python_commands.html',
                           title=_('Review Python Commands'),
                           commands=commands,
                           pagination=pending_commands_pagination)

@bp.route('/python_command/<int:command_id>/update_status', methods=['POST'])
@login_required
@admin_required
def update_python_command_status(command_id):
    """Updates the status of a Python command (approve/reject)."""
    command = PythonCommand.query.get_or_404(command_id)
    new_status = request.form.get('status') # 'approved' or 'rejected'
    notes = request.form.get('review_notes', '')
    allowed_statuses = ['approved', 'rejected']
    
    if new_status in allowed_statuses:
        try:
            command.status = new_status
            command.review_notes = notes.strip() if notes else None
            command.updated_at = datetime.utcnow() # Explicitly update timestamp
            db.session.commit()
            flash(_('Command status updated to %(status)s.', status=new_status), 'success')
            # Optionally notify the user who submitted?
            # notify_user(command.submitted_by_user_id, f"Your Python command '{command.trigger}' was {new_status}")
        except Exception as e:
            db.session.rollback()
            print(f"!!! Error updating Python command status for ID {command_id}: {e}")
            flash(_('Error updating command status.'), 'danger')
    else:
        flash(_('Invalid status provided.'), 'danger')
        
    # Redirect back to the review page
    page = request.args.get('page', 1) 
    return redirect(url_for('admin.review_python_commands', page=page))

# --- End Python Command Review --- 

# TODO: Add routes for user management (edit, delete, make admin etc.) 