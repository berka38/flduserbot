# Kimlik doğrulama view fonksiyonları buraya eklenecek 
from flask import render_template, url_for, flash, redirect
# Buraya formlar ve login işlemleri için importlar eklenecek
from app import db # Veritabanı işlemleri için db import edelim
from . import bp # Göreceli import
from .forms import LoginForm, RegistrationForm # Göreceli import
from app.models import User, Notification # Import Notification model
from flask_login import current_user, login_user, logout_user # Login işlemleri için
from flask_babel import _ # gettext import
import json # Import json for payload

@bp.route('/login', methods=['GET', 'POST']) # Hem GET hem POST isteklerini kabul etsin
def login():
    if current_user.is_authenticated: # Kullanıcı zaten giriş yapmışsa ana sayfaya yönlendir
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash(_('Invalid username or password'), 'danger')
            return redirect(url_for('auth.login'))
        login_user(user, remember=form.remember_me.data)
        # print(f"--- User {user.username} logged in. current_user.is_authenticated: {current_user.is_authenticated}") # Debug print
        flash(_('Login successful!'), 'success')
        # TODO: Giriş sonrası yönlendirme (next parametresi) eklenebilir
        return redirect(url_for('main.index'))
    return render_template('auth/login.html', title='Giriş Yap', form=form)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        # --- Find referrer if code is provided --- 
        referrer = None
        if form.referral_code.data:
            cleaned_code = form.referral_code.data.strip().upper()
            referrer = User.query.filter(User.affiliate_code == cleaned_code).first()
            if referrer:
                print(f"--- Valid referral code '{cleaned_code}' found for user {referrer.username}")
            else:
                 # Optional: Flash a warning if code is invalid, but still allow registration
                 flash(_('Invalid referral code entered, proceeding without referral.'), 'warning')
                 print(f"--- Invalid referral code entered: '{cleaned_code}'")
        # --- End Referrer Check ---
        
        user = User(
            username=form.username.data, 
            email=form.email.data,
            # Set referred_by_id if referrer was found
            referred_by_id=referrer.id if referrer else None 
            )
        user.set_password(form.password.data)
        db.session.add(user)
        
        try: 
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"!!! Error during initial user commit: {e}")
            flash(_("An error occurred during registration. Please try again."), "danger")
            return render_template('auth/register.html', title=_('Register'), form=form)
            
        # --- Generate Affiliate Code --- 
        try:
            user.generate_affiliate_code()
            db.session.add(user)
            db.session.commit()
            print(f"--- Generated affiliate code {user.affiliate_code} for user {user.username}")
        except Exception as e:
            print(f"!!! Error generating affiliate code for user {user.username}: {e}")
        # --- End Affiliate Code Generation ---

        # --- Send notification to all admins --- 
        try:
            admins = User.query.filter_by(role='admin').all()
            if admins:
                payload = json.dumps({'username': user.username})
                for admin in admins:
                    notification = Notification(
                        user_id=admin.id,
                        name='new_user_registered',
                        payload_json=payload
                    )
                    db.session.add(notification)
                db.session.commit()
                print(f"--- Sent 'new_user_registered' notification to {len(admins)} admins for user {user.username}")
            else:
                print("--- No admins found to send registration notification.")
        except Exception as e:
            print(f"!!! Error sending registration notification: {e}")
            db.session.rollback()
        # --- End Notification --- 
            
        flash(_('Congratulations, you are now a registered user! You can now log in.'), 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', title='Kayıt Ol', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    flash(_('You have been logged out successfully.'), 'info')
    return redirect(url_for('main.index')) 