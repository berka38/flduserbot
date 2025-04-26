# Bot yönetimi view fonksiyonları buraya eklenecek 
from flask import render_template, redirect, url_for, flash, current_app, request # request import edildi
from flask_login import login_required, current_user
from . import bp # Göreceli import
from .forms import AddBotForm, EnterCodeForm, AddCustomCommandForm, EditCustomCommandForm, AddPythonCommandForm, SelectAccountForMarketCommandForm # Göreceli import
from app.models import TelegramAccount, CustomCommand, User, Notification, PythonCommand, CommandCategory # Modeli import et
from app import db # db'yi import et
import asyncio # asyncio import edildi
import os # os modülünü import et
from telethon import TelegramClient # Telethon import edildi
from telethon.sessions import StringSession # StringSession import edildi
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError # Hata yakalama için
import subprocess # subprocess import edildi
import sys # sys import edildi
from flask_babel import _ # gettext import
import json # Import json
from sqlalchemy.exc import IntegrityError # Import IntegrityError
# İleride bot ekleme formu ve Telethon işlemleri için importlar eklenecek
# from app.models import TelegramAccount
# from app import db

# Komut limitini burada tanımlayalım (config dosyasına da taşınabilir)
DEFAULT_COMMAND_LIMIT = 5

# Rol bazlı limitleri tanımlayalım
BOT_LIMITS = {
    'user': 1,
    'premium': 5,
    'admin': float('inf') # Admin için sonsuz limit
}

# Define command cost at the top or in config
COMMAND_ADD_COST = 1
REWARD_FOR_MAKING_PUBLIC = 5

@bp.route('/dashboard')
@login_required # Bu sayfaya erişim için giriş yapmış olmak gerekli
def dashboard():
    accounts = current_user.telegram_accounts.order_by(TelegramAccount.id.asc()).all()
    running_bots_dict = current_app.config.get('RUNNING_BOTS', {}) # Get the dict
    return render_template('bot/dashboard.html', title=_('Bot Management Panel'), accounts=accounts, running_bots=running_bots_dict)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_bot():
    # Kullanıcının mevcut bot sayısını al
    current_bot_count = current_user.telegram_accounts.count()
    # Kullanıcının rolüne göre limiti al (rol yoksa user varsay)
    user_role = getattr(current_user, 'role', 'user')
    bot_limit = BOT_LIMITS.get(user_role, BOT_LIMITS['user']) 

    # Limiti kontrol et
    if current_bot_count >= bot_limit:
        limit_value_for_msg = BOT_LIMITS['user'] if user_role == 'user' else BOT_LIMITS['premium']
        flash_msg = _('You have reached the maximum limit of %(limit)s bot accounts for your account type. Upgrade to Premium for more accounts.', limit=limit_value_for_msg)
        flash(flash_msg, 'warning')
        
        # --- Create Notification --- 
        try:
            payload = json.dumps({
                'limit_type': 'bot',
                'limit_value': limit_value_for_msg
            })
            notification = Notification(
                user_id=current_user.id,
                name='limit_reached',
                payload_json=payload
            )
            db.session.add(notification)
            db.session.commit() 
        except Exception as notify_err:
            print(f"!!! Error creating bot limit_reached notification: {notify_err}")
            db.session.rollback()
        # --- End Notification ---
            
        return redirect(url_for('bot.dashboard'))

    form = AddBotForm()
    if form.validate_on_submit():
        # Telefon numarasını temizle (sadece rakamlar ve başta +)
        cleaned_phone = '+' + ''.join(filter(str.isdigit, form.phone_number.data))

        account = TelegramAccount(
            owner=current_user,
            phone_number=cleaned_phone,
            api_id=form.api_id.data,
            api_hash=form.api_hash.data,
            status='pending_login' # Başlangıç durumu
        )
        db.session.add(account)
        db.session.commit()
        flash(_('Telegram account added. You should now initiate the login process.'), 'info') # Bilgi mesajı
        return redirect(url_for('bot.dashboard'))
    else:
        # Log errors if validation fails on POST request
        if form.is_submitted() and not form.validate(): # Check if it was actually a POST request that failed validation
            print("--- Add Bot Form Validation Errors:", form.errors)
            
    return render_template('bot/add_bot.html', title=_('Add New Bot Account'), form=form)

@bp.route('/login/<int:account_id>/start', methods=['GET']) # Sadece GET
@login_required
def start_login(account_id):
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash(_('You do not have permission to access this account.'), 'danger')
        return redirect(url_for('bot.dashboard'))

    if account.status not in ['pending_login', 'error', 'error_session', 'error_2fa_needed']: # Tekrar denenebilir durumlar
        flash(_('Login process for %(phone)s has already been started or completed.', phone=account.phone_number), 'warning')
        return redirect(url_for('bot.dashboard'))

    # Session dosyasını silme işlemi kaldırıldı
    # session_path = f"instance/{current_user.id}_{account.id}.session"
    # try:
    #     if os.path.exists(session_path):
    #         os.remove(session_path)
    #         print(f"--- Deleted existing session file: {session_path}") # Log
    # except Exception as e:
    #     print(f"--- Error deleting session file {session_path}: {e}") # Log
        
    # --- Telethon İşlemleri --- 
    api_id = account.api_id
    api_hash = account.api_hash
    phone = account.phone_number

    async def send_code():
        # Initialize client with StringSession
        session = StringSession() # Yeni StringSession oluştur
        client = TelegramClient(session, api_id, api_hash)
        try:
            print("--- [send_code] Connecting...") # Log
            await client.connect()
            print("--- [send_code] Connected.") # Log
            
            is_auth = await client.is_user_authorized()
            if not is_auth:
                print(f"--- [send_code] Sending code request to {phone}...") # Log
                result = await client.send_code_request(phone)
                print(f"--- [send_code] Code request result: {result}") # Log
                
                # Başarılı, hash'i, bilgileri ve o anki session string'i sakla
                initial_session_string = client.session.save() # Get current session string
                print(f"--- [send_code] Storing pending login info with initial session string (type: {type(initial_session_string)})...") # Log
                current_app.config['PENDING_LOGINS'][account.id] = {
                    'phone_code_hash': result.phone_code_hash,
                    'phone': phone,
                    'api_id': api_id,
                    'api_hash': api_hash,
                    'initial_session': initial_session_string # Store the initial string session
                }
                account.status = 'pending_code'
                db.session.commit()
                flash(_('Verification code sent to %(phone)s.', phone=phone), 'success')
                await client.disconnect() # Disconnect after sending code
                return True # Başarı
            else:
                # Zaten giriş yapılmışsa (StringSession ile beklenmez ama kontrol edelim)
                print("--- [send_code] User already authorized (unexpected with StringSession). Saving final session.") # Log
                final_session_string = client.session.save()
                if isinstance(final_session_string, str) and final_session_string:
                     account.session_string = final_session_string
                     account.status = 'active'
                     db.session.commit()
                     flash(_('Account %(phone)s was already active (session updated).', phone=phone), 'info')
                else:
                    print(f"--- [send_code] Failed to get session string even though authorized.")
                    flash(_('Account %(phone)s was already active but failed to get session.', phone=phone), 'warning')
                    account.status = 'error_session' # Hata durumu
                    db.session.commit()
                
                await client.disconnect()
                return False # Yönlendirme için False
        except FloodWaitError as e:
            print(f"--- [send_code] FloodWaitError: {e}") # Log
            flash(_('Too many attempts. Please try again in %(seconds)s seconds.', seconds=e.seconds), 'danger')
            # --- Create Notification --- 
            try:
                payload = json.dumps({'error_type': 'FloodWaitError', 'seconds': e.seconds, 'phone': phone})
                notification = Notification(user_id=account.owner.id, name='bot_error', payload_json=payload)
                db.session.add(notification)
                db.session.commit()
            except Exception as notify_err:
                print(f"!!! Error creating FloodWaitError notification: {notify_err}")
                db.session.rollback()
            # --- End Notification --- 
            await client.disconnect()
            return False
        except Exception as e:
            print(f"--- [send_code] Generic Exception: {e}") # Log
            import traceback
            print(traceback.format_exc()) # Log traceback
            flash(_('An error occurred while sending the code: %(error)s', error=str(e)), 'danger')
            account.status = 'error' # Hata durumuna al
            db.session.commit()
            # --- Create Notification --- 
            try:
                payload = json.dumps({'error_type': 'SendCodeError', 'message': str(e), 'phone': phone})
                notification = Notification(user_id=account.owner.id, name='bot_error', payload_json=payload)
                db.session.add(notification)
                db.session.commit()
            except Exception as notify_err:
                print(f"!!! Error creating SendCodeError notification: {notify_err}")
                db.session.rollback()
            # --- End Notification --- 
            await client.disconnect()
            return False

    # Asenkron fonksiyonu çalıştır
    try:
        success = asyncio.run(send_code())
        if success:
            return redirect(url_for('bot.login_code', account_id=account.id))
        else:
            return redirect(url_for('bot.dashboard'))
    except RuntimeError as e:
        flash(_("An internal error occurred while starting login: %(error)s", error=str(e)), "danger")
        return redirect(url_for('bot.dashboard'))

@bp.route('/login/<int:account_id>/code', methods=['GET', 'POST'])
@login_required
def login_code(account_id):
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash(_('You do not have permission to access this account.'), 'danger')
        return redirect(url_for('bot.dashboard'))

    if account.status != 'pending_code':
        flash(_('Code entry is not expected for this account.'), 'warning')
        return redirect(url_for('bot.dashboard'))

    # Saklanan bilgileri al
    pending_info = current_app.config['PENDING_LOGINS'].get(account.id)
    if not pending_info:
        flash(_('Login session not found or expired. Please start again.'), 'danger')
        account.status = 'pending_login' # Durumu başa al
        db.session.commit()
        return redirect(url_for('bot.dashboard'))

    form = EnterCodeForm()
    if form.validate_on_submit():
        code = form.code.data
        phone = pending_info['phone']
        phone_code_hash = pending_info['phone_code_hash']
        # session_path = pending_info['session_path'] # Artık session path yok
        api_id = pending_info['api_id']
        api_hash = pending_info['api_hash']
        initial_session = pending_info.get('initial_session') # Başlangıç session string'ini al
        if not initial_session:
            flash(_('Session information missing. Please start login again.'), 'danger')
            account.status = 'pending_login'
            db.session.commit()
            # PENDING_LOGINS temizliği?
            if account.id in current_app.config['PENDING_LOGINS']:
                 del current_app.config['PENDING_LOGINS'][account.id]
            return redirect(url_for('bot.dashboard'))

        # --- Telethon İşlemleri --- 
        async def process_code():
            # Initialize client with the initial StringSession
            session = StringSession(initial_session) 
            client = TelegramClient(session, api_id, api_hash)
            try:
                print("--- [process_code] Connecting...") # Log
                await client.connect()
                print("--- [process_code] Connected.") # Log
                # sign_in fonksiyonunu çağır
                print("--- [process_code] Calling sign_in...") # Log
                signed_in_user = await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
                print(f"--- [process_code] Sign in successful for user: {signed_in_user}") # Log
                
                # Başarılı giriş
                # Yetkilendirilmiş son session string'ini al
                final_session_string = client.session.save() 
                print(f"--- [process_code] Final session string type: {type(final_session_string)}") # Log type

                success_flag = False # Başarı durumunu takip edelim
                if isinstance(final_session_string, str) and final_session_string: # Check if it's a non-empty string
                    account.session_string = final_session_string
                    account.status = 'active'
                    db.session.commit()
                    print("--- [process_code] Final session string successfully saved to DB.") # Log
                    flash(_('Account %(phone)s activated successfully!', phone=phone), 'success')
                    success_flag = True
                else:
                    print(f"--- [process_code] Error: Could not retrieve final session string. Value: {final_session_string}")
                    flash(_('Login successful but failed to retrieve the final session key. The bot cannot be started.'), 'danger')
                    account.status = 'error_session'
                    db.session.commit()
                
                # Check for session string retrieval failure
                if not isinstance(final_session_string, str) or not final_session_string:
                    # --- Create Notification --- 
                    try:
                        payload = json.dumps({'error_type': 'SessionRetrievalError', 'phone': phone})
                        notification = Notification(user_id=account.owner.id, name='bot_error', payload_json=payload)
                        db.session.add(notification)
                        # Already committed status change above, commit notification
                        db.session.commit() 
                    except Exception as notify_err:
                        print(f"!!! Error creating SessionRetrievalError notification: {notify_err}")
                        db.session.rollback()
                    # --- End Notification ---
                    # No need to return here, status already set to error
                    
                # Saklanan bilgileri temizle
                if account.id in current_app.config['PENDING_LOGINS']:
                    del current_app.config['PENDING_LOGINS'][account.id]
                
                print("--- [process_code] Disconnecting...") # Log
                await client.disconnect()
                print("--- [process_code] Disconnected.") # Log
                return success_flag # True if session saved, False otherwise

            except PhoneCodeInvalidError:
                print("--- [process_code] PhoneCodeInvalidError") # Log
                flash(_('The verification code entered is invalid.'), 'danger')
                # --- Create Notification --- 
                try:
                    payload = json.dumps({'error_type': 'PhoneCodeInvalidError', 'phone': phone})
                    notification = Notification(user_id=account.owner.id, name='bot_error', payload_json=payload)
                    db.session.add(notification)
                    db.session.commit()
                except Exception as notify_err:
                    print(f"!!! Error creating PhoneCodeInvalidError notification: {notify_err}")
                    db.session.rollback()
                # --- End Notification ---
                await client.disconnect()
                return False
            except SessionPasswordNeededError:
                 print("--- [process_code] SessionPasswordNeededError") # Log
                 flash(_('Two-factor authentication (2FA) is enabled for this account, which is not currently supported by this tool.'), 'danger')
                 if account.id in current_app.config['PENDING_LOGINS']:
                     del current_app.config['PENDING_LOGINS'][account.id]
                 account.status = 'error_2fa_needed'
                 db.session.commit()
                 # --- Create Notification --- 
                 try:
                     payload = json.dumps({'error_type': 'SessionPasswordNeededError', 'phone': phone})
                     notification = Notification(user_id=account.owner.id, name='bot_error', payload_json=payload)
                     db.session.add(notification)
                     # Already committed status change above, commit notification
                     db.session.commit()
                 except Exception as notify_err:
                     print(f"!!! Error creating SessionPasswordNeededError notification: {notify_err}")
                     db.session.rollback()
                 # --- End Notification ---
                 await client.disconnect()
                 return False
            except FloodWaitError as e:
                 print(f"--- [process_code] FloodWaitError: {e}") # Log
                 flash(_('Too many attempts. Please try again in %(seconds)s seconds.', seconds=e.seconds), 'danger')
                 # --- Create Notification --- 
                 try:
                     payload = json.dumps({'error_type': 'FloodWaitError', 'seconds': e.seconds, 'phone': phone})
                     notification = Notification(user_id=account.owner.id, name='bot_error', payload_json=payload)
                     db.session.add(notification)
                     db.session.commit()
                 except Exception as notify_err:
                     print(f"!!! Error creating FloodWaitError notification (login_code): {notify_err}")
                     db.session.rollback()
                 # --- End Notification ---
                 await client.disconnect()
                 return False
            except Exception as e:
                print(f"--- [process_code] Generic Exception: {e}") # Log
                import traceback
                print(traceback.format_exc()) # Log traceback
                flash(_('An error occurred during code verification: %(error)s', error=str(e)), 'danger')
                if account.id in current_app.config['PENDING_LOGINS']:
                    del current_app.config['PENDING_LOGINS'][account.id]
                account.status = 'error'
                db.session.commit()
                # --- Create Notification --- 
                try:
                    payload = json.dumps({'error_type': 'CodeVerificationError', 'message': str(e), 'phone': phone})
                    notification = Notification(user_id=account.owner.id, name='bot_error', payload_json=payload)
                    db.session.add(notification)
                    # Already committed status change above, commit notification
                    db.session.commit()
                except Exception as notify_err:
                    print(f"!!! Error creating CodeVerificationError notification: {notify_err}")
                    db.session.rollback()
                # --- End Notification ---
                await client.disconnect()
                return False

        # Asenkron fonksiyonu çalıştır
        try:
            print("--- [login_code] Running process_code...") # Log
            success = asyncio.run(process_code())
            print(f"--- [login_code] process_code finished with success={success}") # Log
            return redirect(url_for('bot.dashboard'))
            
        except RuntimeError as e:
            print(f"--- [login_code] RuntimeError: {e}") # Log
            flash(_("An internal error occurred while processing code: %(error)s", error=str(e)), "danger")
            if account.id in current_app.config['PENDING_LOGINS']:
                del current_app.config['PENDING_LOGINS'][account.id]
            account.status = 'error'
            db.session.commit()
            return redirect(url_for('bot.dashboard'))

    # GET isteği için veya form validasyonu başarısızsa
    phone_display = pending_info.get('phone', account.phone_number) # Telefonu göster
    return render_template('bot/login_code.html', title='Doğrulama Kodu Gir', form=form, account_id=account_id, phone=phone_display)

@bp.route('/delete/<int:account_id>', methods=['POST'])
@login_required
def delete_bot(account_id):
    print(f"--- Delete request received for account {account_id}. Form data:", request.form) # Log form data
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash('Bu hesabı silme yetkiniz yok.', 'danger')
        return redirect(url_for('bot.dashboard'))

    phone_number = account.phone_number # Mesaj için sakla
    session_path = f"instance/{current_user.id}_{account.id}.session"
    session_journal_path = session_path + "-journal"

    # Bekleyen giriş varsa temizle
    if account.id in current_app.config['PENDING_LOGINS']:
        try:
            del current_app.config['PENDING_LOGINS'][account.id]
        except KeyError:
            pass # Zaten yoksa sorun değil

    # Session dosyalarını sil
    try:
        if os.path.exists(session_path):
            os.remove(session_path)
            print(f"--- Deleted session file: {session_path}")
        if os.path.exists(session_journal_path):
            os.remove(session_journal_path) # SQLite journal dosyasını da sil
    except Exception as e:
        print(f"--- Error deleting session files for account {account_id}: {e}")
        flash('Hesap veritabanından silindi ancak session dosyaları silinirken bir hata oluştu.', 'warning')
        # --- Create Notification (Warning) --- 
        try:
            payload = json.dumps({'error_type': 'DeleteSessionError', 'message': str(e), 'phone': account.phone_number})
            # Note: User might not want a notification for this, maybe config option?
            notification = Notification(user_id=current_user.id, name='bot_warning', payload_json=payload) # Use different name? 'bot_warning'?
            db.session.add(notification)
            db.session.commit()
        except Exception as notify_err:
            print(f"!!! Error creating DeleteSessionError notification: {notify_err}")
            db.session.rollback()
        # --- End Notification ---

    # Veritabanından sil
    try:
        db.session.delete(account)
        db.session.commit()
        flash(f'{phone_number} numaralı hesap başarıyla silindi.', 'success')
    except Exception as e:
        db.session.rollback() # Hata olursa işlemi geri al
        flash(f'Hesap silinirken bir veritabanı hatası oluştu: {e}', 'danger')

    return redirect(url_for('bot.dashboard'))

@bp.route('/start_runner/<int:account_id>', methods=['POST'])
@login_required
def start_runner(account_id):
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash('Bu botu başlatma yetkiniz yok.', 'danger')
        return redirect(url_for('bot.dashboard'))

    if account.status != 'active' or not account.session_string:
        flash('Bu bot aktif değil veya oturum bilgisi eksik.', 'danger')
        return redirect(url_for('bot.dashboard'))

    if account.id in current_app.config.get('RUNNING_BOTS', {}):
        flash('Bu bot zaten çalışıyor.', 'warning')
        return redirect(url_for('bot.dashboard'))

    # Bot runner script'ini başlat
    python_executable = sys.executable # Get the path to the current Python interpreter
    script_path = os.path.join('bot_core', 'bot_runner.py')
    # --- Set CWD for subprocess --- 
    # Get the absolute path of the project root (one level up from the app directory)
    project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
    print(f"--- [start_runner] Project root calculated as: {project_root}")
    # --- End Set CWD --- 
    
    try:
        # --- Prepare Environment for Subprocess ---
        # Copy the current environment
        env = os.environ.copy()
        # Get the existing PYTHONPATH or default to empty string
        python_path = env.get('PYTHONPATH', '')
        # Prepend the project root to PYTHONPATH, using the OS-specific separator
        env['PYTHONPATH'] = f"{project_root}{os.pathsep}{python_path}"
        print(f"--- [start_runner] Modified PYTHONPATH for subprocess: {env['PYTHONPATH']}")
        # --- End Prepare Environment ---

        print(f"--- [start_runner] Attempting to start process: {python_executable} {script_path} ... in CWD: {project_root}") # Log command and CWD
        process = subprocess.Popen([
            python_executable,
            script_path,
            str(account.api_id),
            account.api_hash,
            account.session_string,
            str(account.id), # Pass account_id
            str(current_user.id) # Pass owner user id
        ],
        cwd=project_root, # Set the working directory to the project root
        env=env # Pass the modified environment with updated PYTHONPATH
        )
        
        # Çalışan süreci kaydet
        current_app.config['RUNNING_BOTS'][account.id] = process
        print(f"--- Started bot runner process for account {account.id} with PID {process.pid}")
        flash(f'{account.phone_number} için bot başarıyla başlatıldı.', 'success')
    except Exception as e:
        print(f"--- Error starting bot runner process for account {account.id}: {e}")
        flash(f'Bot başlatılırken bir hata oluştu: {e}', 'danger')
        # --- Create Notification --- 
        try:
            payload = json.dumps({'error_type': 'StartRunnerError', 'message': str(e), 'phone': account.phone_number})
            notification = Notification(user_id=current_user.id, name='bot_error', payload_json=payload)
            db.session.add(notification)
            db.session.commit()
        except Exception as notify_err:
            print(f"!!! Error creating StartRunnerError notification: {notify_err}")
            db.session.rollback()
        # --- End Notification ---

    return redirect(url_for('bot.dashboard'))

@bp.route('/stop_runner/<int:account_id>', methods=['POST'])
@login_required
def stop_runner(account_id):
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash('Bu botu durdurma yetkiniz yok.', 'danger')
        return redirect(url_for('bot.dashboard'))

    running_bots = current_app.config.get('RUNNING_BOTS', {})
    if account.id not in running_bots:
        flash('Bu bot zaten çalışmıyor.', 'warning')
        return redirect(url_for('bot.dashboard'))

    process = running_bots[account.id]
    try:
        pid = process.pid
        process.terminate() # Süreci sonlandır
        process.wait(timeout=5) # Sonlanmasını bekle (isteğe bağlı timeout)
        print(f"--- Terminated bot runner process for account {account.id} with PID {pid}")
        del running_bots[account.id] # Kayıtlardan çıkar
        flash(f'{account.phone_number} için bot başarıyla durduruldu.', 'success')
    except subprocess.TimeoutExpired:
        print(f"--- Timeout waiting for bot runner process {pid} to terminate. Killing...")
        process.kill()
        process.wait()
        del running_bots[account.id] 
        flash(f'{account.phone_number} için bot zaman aşımı nedeniyle zorla durduruldu.', 'warning')
    except Exception as e:
        print(f"--- Error stopping bot runner process for account {account.id}: {e}")
        flash(f'Bot durdurulurken bir hata oluştu: {e}', 'danger')
        # Hata olsa bile kayıtlardan çıkarmayı dene
        if account.id in running_bots:
            del running_bots[account.id]

    return redirect(url_for('bot.dashboard'))

@bp.route('/<int:account_id>/commands/add', methods=['GET', 'POST'])
@login_required
def add_custom_command(account_id):
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash(_('You do not have permission to add commands to this account.'), 'danger') # Translated
        return redirect(url_for('bot.dashboard'))

    # Kullanıcının rolünü ve komut sayısını kontrol et
    command_count = account.custom_commands.count()
    # Use the is_premium() method from the User model
    if not current_user.is_premium() and not current_user.is_admin() and command_count >= DEFAULT_COMMAND_LIMIT:
        # Translated and using f-string for the limit
        flash(_('You have reached the maximum limit of {limit} custom commands for your account type. Upgrade to Premium for unlimited commands.').format(limit=DEFAULT_COMMAND_LIMIT), 'warning')
        # Redirect to list_commands where the disabled button and message will be shown
        return redirect(url_for('bot.list_custom_commands', account_id=account.id))

    # Formu account_id ile başlat
    form = AddCustomCommandForm(account_id=account.id)
    if form.validate_on_submit():
        new_command = CustomCommand(
            account_id=account.id,
            trigger=form.trigger.data.strip(), # Başındaki/sonundaki boşlukları temizle
            response=form.response.data
        )
        db.session.add(new_command)
        db.session.commit()
        # Translated flash message
        flash(_("Custom command '%(trigger)s' added successfully.").format(trigger=new_command.trigger), 'success')
        # Redirect to the command list page after adding
        return redirect(url_for('bot.list_custom_commands', account_id=account.id)) 
    
    # Pass form and account to the template
    return render_template(
        'bot/add_custom_command.html', 
        # Translated title
        title=_("Add Command for '{phone_number}'").format(phone_number=account.phone_number), 
        form=form, 
        account=account
    )

@bp.route('/<int:account_id>/commands')
@login_required
def list_custom_commands(account_id):
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash('Bu hesabın komutlarını görme yetkiniz yok.', 'danger')
        return redirect(url_for('bot.dashboard'))
    
    # Hesaba ait tüm özel komutları al (ID'ye göre sıralı)
    commands = account.custom_commands.order_by(CustomCommand.id.asc()).all()
    
    # Pass BOT_LIMITS defined at the top of the file to the template context
    return render_template('bot/list_commands.html', 
                           title=f"'{account.phone_number}' Özel Komutları", 
                           account=account, 
                           commands=commands,
                           bot_limits=BOT_LIMITS) # Pass BOT_LIMITS here

@bp.route('/command/<int:command_id>/toggle', methods=['POST'])
@login_required
def toggle_custom_command(command_id):
    command = CustomCommand.query.get_or_404(command_id)
    # Komutun sahibini kontrol et (ilişkili account üzerinden)
    if command.account.owner != current_user:
        flash('Bu komutu değiştirme yetkiniz yok.', 'danger')
        # Nereye yönlendirelim? Belki dashboard daha mantıklı?
        return redirect(url_for('bot.dashboard')) 
    
    # Durumu tersine çevir
    command.is_active = not command.is_active
    db.session.commit()
    
    flash(f"'{command.trigger}' komutu {'aktif' if command.is_active else 'pasif'} hale getirildi.", 'info')
    # Komut listeleme sayfasına geri dön
    return redirect(url_for('bot.list_custom_commands', account_id=command.account_id))

@bp.route('/command/<int:command_id>/delete', methods=['POST'])
@login_required
def delete_custom_command(command_id):
    command = CustomCommand.query.get_or_404(command_id)
    # Yetki kontrolü
    if command.account.owner != current_user:
        flash('Bu komutu silme yetkiniz yok.', 'danger')
        return redirect(url_for('bot.dashboard'))
    
    account_id = command.account_id # Yönlendirme için sakla
    trigger = command.trigger # Mesaj için sakla
    
    try:
        db.session.delete(command)
        db.session.commit()
        flash(f"'{trigger}' komutu başarıyla silindi.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Komut silinirken bir hata oluştu: {e}', 'danger')
        
    # Komut listeleme sayfasına geri dön
    return redirect(url_for('bot.list_custom_commands', account_id=account_id))

@bp.route('/command/<int:command_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_custom_command(command_id):
    command = CustomCommand.query.get_or_404(command_id)
    # Yetki kontrolü
    if command.account.owner != current_user:
        flash('Bu komutu düzenleme yetkiniz yok.', 'danger')
        return redirect(url_for('bot.dashboard'))

    form = EditCustomCommandForm()
    if form.validate_on_submit():
        # Sadece response'ı güncelle (trigger değiştirilemez)
        command.response = form.response.data
        db.session.commit()
        flash(f"'{command.trigger}' komutu başarıyla güncellendi.", 'success')
        return redirect(url_for('bot.list_custom_commands', account_id=command.account_id))
    elif request.method == 'GET':
        # Formu mevcut verilerle doldur
        form.trigger.data = command.trigger
        form.response.data = command.response
        
    return render_template('bot/edit_custom_command.html',
                           title=f"'{command.trigger}' Komutunu Düzenle",
                           form=form,
                           command=command,
                           account=command.account) # Şablonda account bilgisine de ihtiyaç olabilir

# Buraya bot ekleme, silme, komut yönetimi vb. route'lar eklenecek 
# Telegram giriş adımları (kod isteme, kod girme) için yeni route'lar da buraya gelecek. 

# --- Python Command Routes --- 

@bp.route('/<int:account_id>/commands/add_python', methods=['GET', 'POST'])
@login_required
def add_python_command(account_id):
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash(_('You do not have permission to add commands to this account.'), 'danger')
        return redirect(url_for('bot.dashboard'))
        
    # Premium/Admin kontrolü eklendi
    if not current_user.is_premium() and not current_user.is_admin():
        flash(_('Only Premium or Admin users can submit Python commands.'), 'warning')
        # Python komutları listesine yönlendir
        return redirect(url_for('bot.list_python_commands', account_id=account.id))

    form = AddPythonCommandForm(account_id=account.id)
    if form.validate_on_submit():
        try:
            new_py_command = PythonCommand(
                account_id=account.id,
                submitted_by_user_id=current_user.id,
                trigger=form.trigger.data.strip(),
                description=form.description.data,
                code_body=form.code_body.data,
                price=form.price.data,
                status='pending' # Initial status
            )
            
            # Add selected categories
            selected_category_ids = form.categories.data # This gives a list of IDs
            if selected_category_ids:
                categories_to_add = CommandCategory.query.filter(CommandCategory.id.in_(selected_category_ids)).all()
                new_py_command.categories.extend(categories_to_add)
                
            db.session.add(new_py_command)
            db.session.commit()
            flash(_('Python command \'%(trigger)s\' submitted successfully for review.', 
                    trigger=new_py_command.trigger), 'success')
            return redirect(url_for('bot.list_python_commands', account_id=account.id))
        except Exception as e:
            db.session.rollback()
            print(f"!!! Error submitting Python command: {e}")
            flash(_('An error occurred while submitting the command. Please try again.'), 'danger')

    return render_template('bot/add_python_command.html', 
                           title=_('Add Python Command for Account %(phone)s', phone=account.phone_number), 
                           form=form, 
                           account=account)

@bp.route('/<int:account_id>/python_commands')
@login_required
def list_python_commands(account_id):
    """Lists Python commands submitted by the user for a specific account."""
    account = TelegramAccount.query.get_or_404(account_id)
    if account.owner != current_user:
        flash(_('You do not have permission to view commands for this account.'), 'danger')
        return redirect(url_for('bot.dashboard'))
    
    # Query Python commands submitted by the current user for this account
    # Ordered by creation date descending
    py_commands = PythonCommand.query.filter_by(
        account_id=account.id,
        submitted_by_user_id=current_user.id
    ).order_by(PythonCommand.created_at.desc()).all()
    
    return render_template('bot/list_python_commands.html',
                           title=_('My Python Commands for %(phone)s', phone=account.phone_number),
                           account=account,
                           commands=py_commands)

@bp.route('/python_command/<int:command_id>/toggle_public', methods=['POST'])
@login_required
def toggle_python_command_public(command_id):
    """Toggles the public visibility of a user's approved Python command, awarding credits on making public."""
    command = PythonCommand.query.get_or_404(command_id)
    
    # Check ownership and if the command is approved
    if command.submitted_by_user_id != current_user.id:
        flash(_('You do not have permission to modify this command.'), 'danger')
        return redirect(url_for('bot.dashboard')) 
        
    if command.status != 'approved':
        flash(_('Only approved commands can be made public.'), 'warning')
        return redirect(url_for('bot.list_python_commands', account_id=command.account_id))

    # Prevent making copies from the market public again
    if command.original_command_id is not None and not command.is_public:
        flash(_('Commands added from the market cannot be made public again.'), 'warning')
        return redirect(url_for('bot.list_python_commands', account_id=command.account_id))

    # Sadece premium/admin kullanıcıların public yapabilmesini sağla (private yapmaya izin ver)
    if not command.is_public and (not current_user.is_premium() and not current_user.is_admin()):
        flash(_('Only Premium or Admin users can make commands public.'), 'warning')
        return redirect(url_for('bot.list_python_commands', account_id=command.account_id))

    try:
        was_private = not command.is_public
        command.is_public = not command.is_public
        
        success_message = ''
        # --- Removed credit awarding logic ---
        # if was_private and command.is_public:
        #     submitter = command.submitter
        #     if submitter:
        #          submitter.credits += REWARD_FOR_MAKING_PUBLIC
        #          db.session.add(submitter)
        #          status_text = _('public')
        #          success_message = _('Command \'{trigger}\' successfully set to {status} (+{reward} credits).').format(
        #                 trigger=command.trigger, status=status_text, reward=REWARD_FOR_MAKING_PUBLIC
        #             )
        #     else:
        #          status_text = _('public')
        #          success_message = _('Command \'{trigger}\' successfully set to {status} (Could not award credits: Submitter not found).').format(
        #                 trigger=command.trigger, status=status_text
        #             )
        # else:
        status_text = _('public') if command.is_public else _('private')
        success_message = _('Command \'{trigger}\' successfully set to {status}.').format(
                trigger=command.trigger, status=status_text
            )
        
        db.session.add(command)
        db.session.commit()
        flash(success_message, 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"!!! Error toggling public status for Python command {command.id}: {e}")
        flash(_('An error occurred while updating the command status.'), 'danger')
        
    return redirect(url_for('bot.list_python_commands', account_id=command.account_id))

# Route to show account selection form when adding from market
@bp.route('/add_from_market/<int:original_command_id>/select', methods=['GET', 'POST'])
@login_required
def add_command_from_market_select_account(original_command_id):
    """Shows form to select account AND handles adding the command on POST.""" # Updated docstring
    original_command = PythonCommand.query.filter_by(
        id=original_command_id, 
        is_public=True, 
        status='approved'
        ).first_or_404() # Use first_or_404 here

    user_accounts = current_user.telegram_accounts.all()
    
    if not user_accounts:
        flash(_('You need to add a bot account first before adding market commands.'), 'warning')
        return redirect(url_for('main.market'))

    form = SelectAccountForMarketCommandForm(user_accounts=user_accounts)

    if form.validate_on_submit():
        target_account_id = form.account.data
        
        # --- Start: Logic moved from add_command_from_market_add --- 
        
        # --- Get Target Account and Verify Ownership --- 
        target_account = TelegramAccount.query.get(target_account_id)
        # Check if account exists and belongs to current user
        if not target_account or target_account.user_id != current_user.id:
            flash(_('Invalid target account selected.'), 'danger')
            # Instead of redirecting to market, maybe re-render select form?
            return redirect(url_for('bot.add_command_from_market_select_account', original_command_id=original_command_id))
            
        # --- Check Credits --- 
        command_price = original_command.price # Get the command's price
        if current_user.credits < command_price:
             flash(_('You need at least %(cost)s credits to add this command (%(trigger)s). You currently have %(balance)s credits.', 
                     cost=command_price, 
                     trigger=original_command.trigger, 
                     balance=current_user.credits), 'warning')
             # Redirect back to the selection page for this command
             return redirect(url_for('bot.add_command_from_market_select_account', original_command_id=original_command_id))
            
        # --- Check for Trigger Collision --- 
        existing_py_command = PythonCommand.query.filter_by(account_id=target_account.id, trigger=original_command.trigger).first()
        existing_custom_command = CustomCommand.query.filter_by(account_id=target_account.id, trigger=original_command.trigger).first()
        
        if existing_py_command or existing_custom_command:
            flash(_('A command with the trigger \'%(trigger)s\' already exists for the account %(phone)s.', 
                    trigger=original_command.trigger, phone=target_account.phone_number), 'warning')
            return redirect(url_for('bot.add_command_from_market_select_account', original_command_id=original_command_id))

        # --- Create and Save the New Command --- 
        try:
            new_command = PythonCommand(
                account_id=target_account.id,
                submitted_by_user_id=current_user.id, 
                trigger=original_command.trigger, 
                description=original_command.description, 
                code_body=original_command.code_body, 
                status='approved',
                is_public=False, 
                original_command_id=original_command.id, 
                review_notes=f"Copied from Market (Original ID: {original_command.id})" 
            )
            current_user.credits -= command_price # Alıcının kredisini düşür

            # Satıcıyı bul ve kredisini/kazancını artır
            seller = User.query.get(original_command.submitted_by_user_id)
            if seller and seller.id != current_user.id: # Satıcı varsa ve alıcıyla aynı kişi değilse
                seller.credits += command_price
                seller.credits_earned += command_price
                db.session.add(seller) # Değişiklikleri session'a ekle
                print(f"--- Transferred {command_price} credits to seller {seller.id} for command {original_command.id}") # Log
            elif seller and seller.id == current_user.id:
                print(f"--- Self-purchase detected for command {original_command.id}, no credit transfer.") # Log
            else:
                print(f"!!! Could not find seller with ID {original_command.submitted_by_user_id} to transfer credits for command {original_command.id}") # Log

            db.session.add(new_command)
            db.session.add(current_user) # Alıcının kredi değişikliğini session'a ekle
            db.session.commit()
            
            flash(_('Command \'%(trigger)s\' successfully added to account %(phone)s from the market (-%(cost)s credits).', 
                    trigger=new_command.trigger, 
                    phone=target_account.phone_number, 
                    cost=command_price), 'success') # Use actual price in message
            # Redirect to the list of commands for the target account
            return redirect(url_for('bot.list_python_commands', account_id=target_account.id))
            
        except IntegrityError as e:
            db.session.rollback()
            print(f"!!! IntegrityError adding market command {original_command.id} to account {target_account.id}: {e}")
            flash(_('A database error occurred (trigger collision?). Please try again.'), 'danger')
            return redirect(url_for('bot.add_command_from_market_select_account', original_command_id=original_command_id))
        except Exception as e:
            db.session.rollback()
            print(f"!!! Error adding market command {original_command.id} to account {target_account.id}: {e}")
            flash(_('An unexpected error occurred while adding the command.'), 'danger')
            return redirect(url_for('bot.add_command_from_market_select_account', original_command_id=original_command_id))
        # --- End: Logic moved from add_command_from_market_add --- 

    # GET request or form validation failed: Render the selection template
    return render_template('bot/add_from_market_select.html',
                           title=_('Add Market Command'),
                           command=original_command,
                           form=form)

# --- Route Removed: add_command_from_market_add --- 
# The logic has been moved into the POST handler of add_command_from_market_select_account

# TODO: Add routes for editing/deleting pending python commands?

# --- End Python Command Routes --- 