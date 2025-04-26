import sys
import asyncio
import os
import pkgutil
import importlib
import re # Regex için import
import traceback # For detailed error logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from sqlalchemy import create_engine # SQLAlchemy importları
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime, timedelta # datetime import
from app.models import CustomCommand, TelegramAccount, User, Notification, PythonCommand, AnimalSpecies, UserAnimal # Import Notification
import json # Import json
import random # Import random
import logging # Import logging

# Add project root to sys.path to allow absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"--- Added project root to sys.path: {project_root}")

# Import config and models after setting sys.path
from config import Config # Config import

# Aylık komut kullanım limitini tanımla
MONTHLY_COMMAND_LIMIT = 100

# --- Game Constants ---
HUNT_COOLDOWN = timedelta(seconds=15) # Cooldown between hunts
# Rarity weights (adjust as needed)
RARITY_WEIGHTS = {
    "Common": 70,
    "Uncommon": 20,
    "Rare": 7,
    "Epic": 2.5,
    "Mythical": 0.5
}
# --- End Game Constants ---

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Setup --- 
def setup_database():
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    # session_factory provides thread-local sessions
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    print("--- Database session configured for bot_runner.")
    return Session

# Veritabanı oturumunu global yapalım (veya main içinde oluşturup pass edelim)
# Global yapmak basitlik için şimdilik uygun olabilir.
db_session = setup_database()

# Komutların bulunduğu klasör
COMMANDS_DIR = os.path.join(os.path.dirname(__file__), "commands")

def load_fixed_commands(client, me_id, account_id):
    """Dynamically loads command handlers from the commands directory."""
    print(f"--- Loading fixed commands from: {COMMANDS_DIR} for account {account_id}")
    for importer, modname, ispkg in pkgutil.iter_modules([COMMANDS_DIR]):
        if not ispkg and modname != "__init__":
            try:
                module_path = f"bot_core.commands.{modname}"
                print(f"--- Importing module: {module_path}")
                module = importlib.import_module(module_path)
                
                # Check if it has a register function and call it with account_id
                if hasattr(module, 'register') and callable(module.register):
                    # Pass account_id to the register function
                    module.register(client, me_id, account_id) 
                else:
                    print(f"Warning: Module '{modname}' does not have a callable 'register' function.")
            except Exception as e:
                print(f"Error loading command module '{modname}': {e}")
                import traceback
                print(traceback.format_exc())
    print("--- Finished loading fixed commands.")

def load_custom_commands(client, me_id, account_id):
    """Loads custom text-based commands from the database for the given account_id."""
    print(f"--- Loading custom text commands for account_id: {account_id}")
    session = None # Initialize session
    try:
        session = db_session() # Yeni bir session al
        commands = session.query(CustomCommand).filter_by(account_id=account_id, is_active=True).all()
        print(f"--- Found {len(commands)} active custom commands in DB.")

        for command in commands:
            trigger = command.trigger
            response = command.response
            current_account_id = command.account_id # account_id'yi sakla
            print(f"--- Registering custom text command: Trigger='{trigger}', Response='{response[:30]}...'")

            # Dinamik olarak handler fonksiyonu oluştur, account_id'yi parametre olarak al
            async def create_custom_handler(event, resp=response, acc_id=current_account_id):
                handler_session = None # Handler için ayrı session
                try:
                    handler_session = db_session() # Yeni session al
                    # Kullanıcıyı ve hesabı bul
                    acc = handler_session.query(TelegramAccount).get(acc_id)
                    if not acc or not acc.owner:
                        print(f"!!! Error: Could not find User for account {acc_id}")
                        return # Kullanıcı bulunamazsa işlem yapma
                    
                    user = acc.owner
                    print(f"--- Custom text command '{event.pattern_match.string}' triggered by user {user.username} ({user.id})")

                    # Kullanım limitini kontrol et
                    if not user.can_use_command(MONTHLY_COMMAND_LIMIT):
                        limit_msg = f"You have reached your monthly command usage limit ({MONTHLY_COMMAND_LIMIT}). Upgrade for more."
                        await event.reply(limit_msg)
                        print(f"--- User {user.username} reached command limit.")
                        
                        # --- Create Notification --- 
                        try:
                            payload = json.dumps({
                                'limit_type': 'command',
                                'limit_value': MONTHLY_COMMAND_LIMIT
                            })
                            notification = Notification(
                                user_id=user.id,
                                name='limit_reached',
                                payload_json=payload
                            )
                            handler_session.add(notification)
                            handler_session.commit() 
                        except Exception as notify_err:
                            print(f"!!! Error creating limit_reached notification: {notify_err}")
                            handler_session.rollback() 
                        # --- End Notification ---
                            
                        return # Komutu çalıştırma

                    # Limite ulaşılmadıysa, sayacı artır
                    user.increment_command_usage()
                    handler_session.commit()
                    print(f"--- Incremented command usage for user {user.username}. New count: {user.command_usage_count}")

                    # Komutu çalıştır
                    print(f"--- Responding to custom text command '{trigger}'...")
                    await event.reply(resp)
                    print("--- Custom text command response sent.")
                    
                except Exception as e:
                    print(f"Error handling custom text command '{trigger}': {e}")
                    if handler_session: 
                        handler_session.rollback() # Hata durumunda rollback
                finally:
                    if handler_session:
                        db_session.remove() # Session'ı thread'den kaldır
            
            pattern_str = trigger
            if not trigger.startswith(('!', '/', '.')): # Common command prefixes
                 pattern_str = rf'(?i)\b{re.escape(trigger)}\b' 
            else:
                 pattern_str = rf'(?i)^{re.escape(trigger)}(?:\s+.*|$)' # Allow args after command
            
            client.add_event_handler(
                create_custom_handler,
                events.NewMessage(from_users=me_id, pattern=pattern_str) 
            )

    except Exception as e:
        print(f"!!! Error loading custom text commands from database: {e}")
        print(traceback.format_exc())
        if session: 
            session.rollback()
    finally:
        if session is not None or db_session.registry.has():
             db_session.remove() 
    print("--- Finished loading custom text commands.")

def load_python_commands(client, me_id, account_id):
    """Loads APPROVED Python commands from the database for the given account_id."""
    print(f"--- Loading APPROVED Python commands for account_id: {account_id}")
    session = None 
    try:
        session = db_session() 
        # Query for APPROVED Python commands for this account
        commands = session.query(PythonCommand).filter_by(
            account_id=account_id, 
            status='approved' # Only load approved commands
        ).all()
        print(f"--- Found {len(commands)} approved Python commands in DB.")

        for command in commands:
            trigger = command.trigger
            code_body = command.code_body
            current_account_id = command.account_id
            command_id_for_log = command.id # For logging
            print(f"--- Registering Python command: Trigger='{trigger}', ID={command_id_for_log}")

            async def create_python_handler(event, cmd_code=code_body, acc_id=current_account_id, cmd_trigger=trigger, cmd_id=command_id_for_log):
                """Dynamically created handler for executing a Python command."""
                handler_session = None 
                try:
                    handler_session = db_session() 
                    acc = handler_session.query(TelegramAccount).get(acc_id)
                    if not acc or not acc.owner:
                        print(f"!!! PyCmd Error: Could not find User for account {acc_id} (Command ID: {cmd_id})")
                        return
                    
                    user = acc.owner
                    print(f"--- Python command '{cmd_trigger}' (ID: {cmd_id}) triggered by user {user.username} ({user.id})")

                    # --- Check Usage Limit ---
                    if not user.can_use_command(MONTHLY_COMMAND_LIMIT):
                        limit_msg = f"You have reached your monthly command usage limit ({MONTHLY_COMMAND_LIMIT})."
                        await event.reply(limit_msg)
                        print(f"--- User {user.username} reached command limit attempting PyCmd {cmd_trigger}.")
                        return
                    
                    # --- Prepare Execution Context ---
                    # WARNING: Using exec() is highly insecure. The executed code runs with the 
                    # same permissions as the bot runner process. Implement sandboxing (e.g., 
                    # restricted_python, separate process/container) for production.
                    
                    # Define a safe reply function for the executed code
                    async def safe_reply(message):
                        try:
                            await event.reply(str(message))
                        except Exception as reply_err:
                            print(f"!!! PyCmd Error (ID: {cmd_id}): Failed to send reply: {reply_err}")

                    # Define the environment for exec(). Only expose necessary and safe objects.
                    # Avoid passing the full 'client' or 'db_session' directly if possible.
                    # Provide specific helper functions instead.
                    exec_globals = {
                        '__builtins__': {}, # VERY IMPORTANT: Restrict builtins
                        'asyncio': asyncio, # Allow async operations if needed
                        'event': event,     # Expose the event object (message, chat_id, etc.)
                        'reply': safe_reply,# Provide the safe reply function
                        'print': lambda *args, **kwargs: print(f"[PyCmd ID:{cmd_id}]", *args, **kwargs), # Capture print statements
                    }
                    exec_locals = {}

                    # --- Execute the User's Code ---
                    print(f"--- Executing Python code for command '{cmd_trigger}' (ID: {cmd_id})...")
                    try:
                        # IMPORTANT: Run exec in an asyncio task if the code might block
                        # For simplicity now, running directly, but beware of blocking code.
                        # exec() doesn't directly support await, need careful handling for async user code.
                        # A simple approach: wrap user code in an async def and run it.
                        
                        # Wrap the user code in an async function
                        wrapped_code = f"async def user_script():\n"
                        wrapped_code += "\n".join([f"    {line}" for line in cmd_code.splitlines()])
                        
                        # Execute the definition of the wrapper function
                        exec(wrapped_code, exec_globals, exec_locals) 
                        
                        # Get the defined async function and run it
                        user_script_func = exec_locals.get('user_script')
                        if user_script_func and asyncio.iscoroutinefunction(user_script_func):
                           await user_script_func() 
                        else:
                           print(f"!!! PyCmd Error (ID: {cmd_id}): Could not find or run async user_script() function in provided code.")
                           await safe_reply("Error: Could not execute the script function.")

                        print(f"--- Finished executing Python code for command '{cmd_trigger}' (ID: {cmd_id}).")

                    except Exception as exec_err:
                        print(f"!!! PyCmd Execution Error (ID: {cmd_id}, Trigger: '{cmd_trigger}'): {exec_err}")
                        print(traceback.format_exc()) # Log detailed traceback
                        try:
                            # Notify user about the error
                            await safe_reply(f"Error executing script for command '{cmd_trigger}':\n```\n{traceback.format_exc(limit=150)}\n```")
                        except Exception as report_err:
                            print(f"!!! PyCmd Error (ID: {cmd_id}): Failed to report execution error to user: {report_err}")

                    # --- Increment Usage Count (AFTER potential limit check) ---
                    user.increment_command_usage()
                    handler_session.commit() # Commit usage increment
                    print(f"--- Incremented command usage for user {user.username} after PyCmd '{cmd_trigger}'. New count: {user.command_usage_count}")

                except Exception as e:
                    print(f"!!! Error in Python command handler for trigger '{cmd_trigger}' (ID: {cmd_id}): {e}")
                    print(traceback.format_exc())
                    if handler_session: 
                        handler_session.rollback() 
                finally:
                    if handler_session:
                        db_session.remove() 

            # --- Register Event Handler ---
            pattern_str = trigger
            # Same pattern logic as custom text commands
            if not trigger.startswith(('!', '/', '.')): 
                 pattern_str = rf'(?i)\b{re.escape(trigger)}\b' 
            else:
                 pattern_str = rf'(?i)^{re.escape(trigger)}(?:\s+.*|$)' 

            client.add_event_handler(
                create_python_handler,
                events.NewMessage(from_users=me_id, pattern=pattern_str) 
            )

    except Exception as e:
        print(f"!!! Error loading Python commands from database: {e}")
        print(traceback.format_exc())
        if session: 
            session.rollback()
    finally:
        if session is not None or db_session.registry.has():
             db_session.remove() 
    print("--- Finished loading Python commands.")

async def main(api_id, api_hash, session_string, account_id, owner_user_id):
    print(f"Starting bot runner for account_id {account_id}...")
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)

    print("Connecting to Telegram...")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("Error: User is not authorized. Session might be invalid.")
            db_session.remove()
            return
        
        me = await client.get_me()
        print(f"Successfully connected as {me.username} ({me.id})")
        
        # Load fixed commands first
        load_fixed_commands(client, me.id, account_id)
        
        # Load custom text command handlers from DB
        load_custom_commands(client, me.id, account_id)

        # Load custom Python command handlers from DB
        load_python_commands(client, me.id, account_id) # Call the new function

        print("Bot runner started. Listening for commands...")
        await client.run_until_disconnected()

    except Exception as e:
        print(f"Error during bot execution: {e}")
        print(traceback.format_exc()) # Log detailed traceback
    finally:
        if client.is_connected():
            print("Disconnecting client...")
            await client.disconnect()
        db_session.remove() # Clean up the main session
        print("Bot runner stopped.")

if __name__ == "__main__":
    # Expecting 5 arguments now
    if len(sys.argv) != 6:
        print("Usage: python bot_runner.py <api_id> <api_hash> <session_string> <account_id> <owner_user_id>")
        sys.exit(1)
    
    api_id_arg = sys.argv[1]
    api_hash_arg = sys.argv[2]
    session_string_arg = sys.argv[3]
    account_id_arg = int(sys.argv[4]) # account_id'yi integer olarak al
    owner_user_id_arg = int(sys.argv[5]) if len(sys.argv) > 5 else None # Get owner_id if provided

    try:
        asyncio.run(main(api_id_arg, api_hash_arg, session_string_arg, account_id_arg, owner_user_id_arg))
    except KeyboardInterrupt:
        print("Bot runner stopped by user.")

# --- Helper Functions ---
async def get_db_user(telethon_user_id):
    """Gets the User object from DB based on Telethon user ID."""
    # This assumes the User model has a telegram_user_id field
    # We need to add this field to the User model!
    # For now, we'll assume the bot only responds to its owner via DM or saved messages
    # In a group setting, we would need a way to map sender_id to our User model
    # Let's assume direct usage where sender_id matches owner for now.
    # THIS NEEDS REVISION LATER
    with app.app_context():
        # We don't have telegram_user_id on User model yet.
        # Let's try finding the user who owns the account running this script?
        # This won't work correctly if multiple users use the system.
        # TEMP HACK: Assume the first user is the owner. VERY BAD.
        # user = User.query.first() 
        # A better approach: Pass the owner's user_id when starting the script?
        # Let's modify the script startup to pass owner_user_id
        if owner_user_id:
            user = User.query.get(owner_user_id)
            return user
    return None

def get_random_animal_by_rarity(rarity):
    """Gets a random AnimalSpecies of the specified rarity."""
    with app.app_context():
        species_list = AnimalSpecies.query.filter_by(rarity=rarity).all()
        if species_list:
            return random.choice(species_list)
    return None

# --- Main Bot Logic --- 
@client.on(events.NewMessage(outgoing=True)) # Listen for outgoing messages (commands sent by the userbot)
async def command_handler(event):
    message_text = event.raw_text
    sender_id = event.sender_id # This should be the userbot's own ID
    chat_id = event.chat_id
    logger.info(f"Outgoing message detected: {message_text} from {sender_id} in chat {chat_id}")

    # --- Get User from DB (NEEDS REFINEMENT) ---
    # Use the owner_user_id passed during startup
    db_user = None
    if owner_user_id:
         with app.app_context():
             db_user = User.query.get(owner_user_id)
    
    if not db_user:
        logger.warning(f"Could not find database user for owner ID {owner_user_id}. Commands might fail.")
        # Decide whether to return or continue without user context
        # return 

    # --- Built-in Game Command Handling ---
    if message_text.lower() == '!hunt':
        logger.info(f"!hunt command received from user {db_user.username if db_user else 'Unknown'}")
        if not db_user:
             await event.edit("[System Error] Could not identify user.")
             return
             
        with app.app_context():
            now = datetime.utcnow()
            # Check cooldown
            if db_user.last_hunt_at and (now - db_user.last_hunt_at) < HUNT_COOLDOWN:
                wait_time = HUNT_COOLDOWN - (now - db_user.last_hunt_at)
                await event.edit(f"⏱️ Please wait {int(wait_time.total_seconds()) + 1} more seconds before hunting again.")
                return

            # Determine caught rarity
            rarities = list(RARITY_WEIGHTS.keys())
            weights = list(RARITY_WEIGHTS.values())
            chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]

            # Get an animal of that rarity
            caught_animal = get_random_animal_by_rarity(chosen_rarity)

            if not caught_animal:
                logger.error(f"No animals found for rarity '{chosen_rarity}'! Check seed data.")
                await event.edit("[System Error] Could not find an animal to hunt. Please tell the admin.")
                return

            # Update user inventory
            user_animal_record = UserAnimal.query.filter_by(user_id=db_user.id, animal_species_id=caught_animal.id).first()
            if user_animal_record:
                user_animal_record.quantity += 1
                user_animal_record.last_updated_at = now
            else:
                user_animal_record = UserAnimal(user_id=db_user.id, animal_species_id=caught_animal.id, quantity=1)
                db.session.add(user_animal_record)

            # Update last hunt time and commit
            db_user.last_hunt_at = now
            db.session.add(db_user) # Add user to session since we modified it
            try:
                db.session.commit()
                logger.info(f"User {db_user.username} caught a {caught_animal.name}.")
                await event.edit(f"🎣 You went hunting and caught a **{caught_animal.rarity}** {caught_animal.emoji} **{caught_animal.name}**!")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Database error during hunt for user {db_user.username}: {e}")
                await event.edit("[System Error] Failed to save hunt result.")
        return # Stop processing after handling built-in command

    # --- !sell command --- 
    elif message_text.lower().startswith('!sell'):
        logger.info(f"!sell command received from user {db_user.username if db_user else 'Unknown'}")
        if not db_user:
             await event.edit("[System Error] Could not identify user.")
             return

        parts = message_text.split()
        total_value = 0
        sold_summary_list = [] # Keep track of what was sold
        something_sold = False

        with app.app_context():
            inventory = db_user.animal_inventory.join(AnimalSpecies).options(db.contains_eager(UserAnimal.species)).all() # Eager load species
            
            if not inventory:
                 await event.edit("🧺 You have no animals in your inventory to sell!")
                 return

            target_name = None
            sell_all = False
            quantity_to_sell = -1 # Default: sell all of the target type

            # --- Parse command arguments --- 
            if len(parts) == 1: # !sell (implies sell all)
                sell_all = True
            elif len(parts) >= 2:
                if parts[1].lower() == 'all':
                    sell_all = True
                else:
                    # Try to parse quantity if provided at the end
                    try:
                        last_part_int = int(parts[-1])
                        if last_part_int > 0 and len(parts) >= 3:
                            quantity_to_sell = last_part_int
                            target_name = " ".join(parts[1:-1]) # Join parts between !sell and quantity
                        else: 
                            # Only one word after !sell, treat as name
                            target_name = " ".join(parts[1:]) 
                            quantity_to_sell = -1 # Sell all of this type
                    except ValueError:
                        # Last part wasn't a number, assume it's part of the name
                        target_name = " ".join(parts[1:])
                        quantity_to_sell = -1 # Sell all of this type
            
            # --- Identify animals to process --- 
            animals_to_process = []
            if sell_all:
                animals_to_process = inventory # Process all items in inventory
                logger.info(f"User {db_user.username} trying to sell ALL animals.")
            elif target_name:
                # Find the target species in the user's inventory
                found = False
                target_name_lower = target_name.lower()
                for item in inventory:
                    # Match by name or emoji
                    if item.species.name.lower() == target_name_lower or item.species.emoji == target_name:
                        animals_to_process.append(item) # Add the specific UserAnimal record
                        found = True
                        break # Found the specific animal type
                if not found:
                    await event.edit(f"❌ Could not find '{target_name}' in your inventory.")
                    return
                logger.info(f"User {db_user.username} trying to sell {quantity_to_sell if quantity_to_sell > 0 else 'all'} of {target_name}.")
            else: # Should not happen if parsing is correct
                 await event.edit("Invalid sell command format. Use `!sell <name|emoji> [quantity]` or `!sell all`.")
                 return
                 
            # --- Process selling --- 
            if not animals_to_process:
                # This case happens if target_name was specified but not found
                # Error message handled above
                return 

            items_to_delete = [] # Track items fully sold
            for item in animals_to_process:
                sell_qty = 0
                # Determine quantity to sell for this item
                if sell_all: 
                    sell_qty = item.quantity
                elif quantity_to_sell == -1: # Sell all of the specific type
                    sell_qty = item.quantity
                elif quantity_to_sell > 0: # Sell specific quantity of the target type
                    sell_qty = min(item.quantity, quantity_to_sell)
                
                if sell_qty > 0:
                    value = item.species.base_value * sell_qty
                    total_value += value
                    item.quantity -= sell_qty
                    something_sold = True
                    sold_summary_list.append(f"{sell_qty}x {item.species.emoji}")
                    logger.info(f"Processed sell: {db_user.username} sold {sell_qty} {item.species.name} for {value} credits. Remaining: {item.quantity}")
                    
                    if item.quantity == 0:
                        items_to_delete.append(item)
            
            # --- Finalize transaction --- 
            if something_sold:
                try:
                    # Update credits
                    db_user.credits += total_value
                    db.session.add(db_user)
                    # Delete items with quantity 0
                    for item_to_del in items_to_delete:
                        db.session.delete(item_to_del)
                    db.session.commit()
                    sold_summary_str = ", ".join(sold_summary_list)
                    await event.edit(f"💰 Sold {sold_summary_str} for **{total_value}** credits! Your new balance is **{db_user.credits}** credits.")
                    logger.info(f"User {db_user.username} successfully sold items. Total value: {total_value}. New balance: {db_user.credits}")
                except Exception as e:
                     db.session.rollback()
                     logger.error(f"Database error during sell for user {db_user.username}: {e}")
                     await event.edit("[System Error] Failed to save sell transaction.")
            else:
                # This happens if quantity was specified but user didn't have enough
                await event.edit(f"❌ You don't have {quantity_to_sell} '{target_name}' to sell.")
        return # Stop processing
        
    # --- !zoo command --- 
    elif message_text.lower() == '!zoo':
         # TODO: Implement !zoo
         await event.edit("[ WIP ] !zoo command coming soon!")
         return

    # --- Existing Command Handling --- 
    # Check for custom commands first
    with app.app_context():
        custom_command = CustomCommand.query.filter_by(account_id=account_id, trigger=message_text, is_active=True).first()
        if custom_command:
            logger.info(f"Found active custom command '{message_text}'")
            try:
                await event.edit(custom_command.response)
                logger.info(f"Edited message with response for custom command '{message_text}'")
            except FloodWaitError as fwe:
                 logger.warning(f"Flood wait error editing message for custom command: {fwe.seconds}s")
                 await asyncio.sleep(fwe.seconds + 1) # Wait and maybe retry?
            except Exception as e:
                logger.error(f"Error editing message for custom command '{message_text}': {e}")
            return # Stop processing if custom command found

    # Check for Python commands if no custom command matched
    if message_text.startswith('!'):
        # ... (keep existing PythonCommand check and execution logic) ...
         with app.app_context():
            python_command = PythonCommand.query.filter_by(account_id=account_id, trigger=message_text, status='approved').first()
            if python_command:
                logger.info(f"Found approved Python command '{message_text}'")
                # --- Execute Python Code --- 
                # Warning: Consider security implications carefully!
                # Use a restricted environment/sandbox if possible.
                # For now, basic exec with limited context.
                
                # Prepare context for the executed code
                exec_globals = {
                    'client': client, 
                    'event': event, 
                    'logger': logger,
                    'asyncio': asyncio,
                    # Add other safe utilities or data access functions here
                    # 'db_session': db.session, # Be VERY careful exposing db session
                    # 'current_db_user': db_user # Expose user? Careful!
                }
                exec_locals = {}
                
                try:
                    # Wrap the user's code in an async function to allow awaits
                    user_code = f"async def __user_code_wrapper():\n" \
                                + "\n".join([f"    {line}" for line in python_command.code_body.splitlines()])
                    
                    logger.debug(f"Executing Python code:\n{user_code}")
                    exec(user_code, exec_globals, exec_locals)
                    
                    # Get the wrapper function and run it
                    user_func = exec_locals.get('__user_code_wrapper')
                    if user_func and asyncio.iscoroutinefunction(user_func):
                        await user_func() 
                        logger.info(f"Successfully executed Python command '{message_text}'")
                    else:
                        logger.error(f"Could not find or execute async wrapper for Python command '{message_text}'")
                        # Don't edit the original message, maybe log error
                        
                except Exception as e:
                    logger.error(f"Error executing Python command '{message_text}': {e}")
                    # Optionally edit the message to show an error, but be careful
                    # await event.edit(f"[Error executing {message_text}: {e}]")
                # --- End Execute Python Code ---
                return # Stop processing

    # If no command matched, log it (optional)
    logger.info(f"No matching command found for outgoing message: {message_text}")

async def main():
    logger.info("Bot runner starting...")
    await client.start()
    logger.info("Client started. Bot is running.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main()) 