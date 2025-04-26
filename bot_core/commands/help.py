from telethon import events
import pkgutil
import importlib
import os
from flask_babel import _

COMMAND_NAME = "help"
COMMAND_DESC = "Mevcut komutların listesini gösterir."

# Komutları dinamik olarak bulmak için commands klasörünün yolu
COMMANDS_PATH = os.path.dirname(__file__)

async def handler(event):
    """Handles the !help command."""
    help_text = "**Mevcut Komutlar:**\n\n"
    
    # Komutları dinamik olarak bul ve listele
    try:
        print("--- [Help Command] Discovering commands...")
        for importer, modname, ispkg in pkgutil.iter_modules([COMMANDS_PATH]):
            if not ispkg and modname != "__init__":
                try:
                    module = importlib.import_module(f".{modname}", package='bot_core.commands')
                    cmd_name = getattr(module, 'COMMAND_NAME', None)
                    cmd_desc = getattr(module, 'COMMAND_DESC', 'Açıklama yok')
                    if cmd_name:
                        help_text += f"`!{cmd_name}` - {cmd_desc}\n"
                        print(f"--- [Help Command] Found command: !{cmd_name}")
                except Exception as e:
                    print(f"--- [Help Command] Error importing/reading module {modname}: {e}")
        print("--- [Help Command] Command discovery finished.")
            
    except Exception as e:
        print(f"--- [Help Command] Error during command discovery: {e}")
        help_text = "Komutlar listelenirken bir hata oluştu."

    try:
        print(f"Received !{COMMAND_NAME} command. Responding...")
        await event.edit(help_text, parse_mode='md') # Markdown formatında gönder
        print("Help response sent.")
    except Exception as e:
        print(f"Error handling !{COMMAND_NAME}: {e}")

def register(client, me_id, account_id):
    """Registers the command handler with the client."""
    client.add_event_handler(
        handler,
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}$')
    )
    print(f"Command '!{COMMAND_NAME}' registered.") 