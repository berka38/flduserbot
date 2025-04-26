from telethon import events
import random
from flask_babel import _

COMMAND_NAME = "zar"
COMMAND_DESC = "Rastgele 1-6 arası bir zar atar."

async def handler(event):
    """Handles the !zar command."""
    try:
        result = random.randint(1, 6)
        await event.edit(f"🎲 Zar sonucu: **{result}**")
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