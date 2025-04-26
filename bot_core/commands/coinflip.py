from telethon import events
import random
from flask_babel import _

COMMAND_NAME = "yazitura"
COMMAND_DESC = "Yazı veya tura atar."

async def handler(event):
    """Handles the !yazitura command."""
    try:
        result = random.choice(["Yazı", "Tura"])
        await event.edit(f"🪙 Sonuç: **{result}**")
    except Exception as e:
        await event.edit(f"Hata: {e}")
        print(f"Error handling !{COMMAND_NAME}: {e}")

def register(client, me_id, account_id):
    """Registers the command handler with the client."""
    client.add_event_handler(
        handler,
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}$')
    )
    print(f"Command '!{COMMAND_NAME}' registered.") 