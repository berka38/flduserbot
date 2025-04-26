from telethon import events, functions, types
import time
from datetime import datetime
import os, sys
from sqlalchemy.orm import scoped_session
from bot_core.bot_runner import db_session, MONTHLY_COMMAND_LIMIT
from app.models import User, TelegramAccount, Notification
from flask_babel import _
import functools # Import functools for partial
import json # Import json

COMMAND_NAME = "online"
COMMAND_DESC = "Gruptaki çevrimiçi kullanıcıları gösterir."

# Modify handler to accept account_id (passed via partial)
async def handler(event, account_id):
    """Handles the !online command, checking usage limits first."""
    handler_session = None
    try:
        handler_session = db_session() # Get DB session
        
        # --- Fetch the correct user using the provided account_id --- 
        account = handler_session.query(TelegramAccount).get(account_id)
        if not account or not account.owner:
             print(f"!!! [online.py] Error: Could not find User for account {account_id}")
             # Rollback or remove session?
             # We didn't change anything, so just remove is fine
             db_session.remove()
             return
        user = account.owner
        # --- User fetched correctly --- 

        print(f"Received !{COMMAND_NAME} command via account {account_id} by user {user.username}. Processing...")

        # Check usage limit
        if not user.can_use_command(MONTHLY_COMMAND_LIMIT):
            limit_msg = _("You have reached your monthly command usage limit (%(limit)s). Upgrade to Premium for unlimited usage.") % {'limit': MONTHLY_COMMAND_LIMIT}
            await event.reply(limit_msg)
            print(f"--- User {user.username} reached command limit for !{COMMAND_NAME}.")
            
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
                handler_session.commit() # Save potential reset & notification
            except Exception as notify_err:
                print(f"!!! Error creating limit_reached notification in {COMMAND_NAME}: {notify_err}")
                handler_session.rollback() # Rollback only notification
            # --- End Notification ---
            
            return # Stop command execution

        # Increment usage if limit not reached
        user.increment_command_usage()
        handler_session.commit() # Save increment/reset
        print(f"--- Incremented command usage for user {user.username} (!{COMMAND_NAME}). New count: {user.command_usage_count}")

        # --- Original Command Logic --- 
        chat = await event.get_chat()
        if not hasattr(chat, 'participants_count'):
            await event.edit(_("This command only works in groups!"))
            return

        await event.edit(_("🔍 Fetching online users..."))
        
        result = await event.client(functions.messages.GetOnlinesRequest(peer=event.chat_id))
        
        current_time = datetime.now().strftime('%H:%M:%S')
        
        if hasattr(result, 'onlines') and result.onlines > 0:
            online_count = result.onlines
            response = _("🟢 **Online Users:** %(count)s\n⏰ *%(time)s*") % {'count': online_count, 'time': current_time}
        else:
            response = _("🔴 **No online users currently**\n⏰ *%(time)s*") % {'time': current_time}
        
        await event.edit(response)
        print(f"Online users response sent. Found {getattr(result, 'onlines', 0)} online users.")
        
    except Exception as e:
        print(f"Error handling !{COMMAND_NAME} for account {account_id}: {e}")
        if handler_session: handler_session.rollback()
        try:
            await event.edit(_("❌ Error: %(error)s") % {'error': str(e)})
        except:
            pass
    finally:
        if handler_session:
            db_session.remove()

# Modify register to accept account_id
def register(client, me_id, account_id):
    """Registers the command handler with the client, passing account_id."""
    
    # Create a partial function that includes the account_id
    partial_handler = functools.partial(handler, account_id=account_id)
    # Make sure Telethon event dispatcher can handle the partial, 
    # or adjust how parameters are passed if needed.
    # Telethon generally passes `event` as the first argument.
    
    # If Telethon doesn't directly support partials with extra args in this way,
    # we might need a wrapper async function.
    # async def handler_wrapper(event):
    #     await handler(event, account_id=account_id)
    # handler_to_register = handler_wrapper 
    # Let's try with partial first.
    
    print(f"--- Registering '!{COMMAND_NAME}' for account {account_id}")
    client.add_event_handler(
        partial_handler, 
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}$')
    )
    # print(f"Command '!{COMMAND_NAME}' registered for account {account_id}.") # Redundant log 