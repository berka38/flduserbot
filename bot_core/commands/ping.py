from telethon import events
from datetime import datetime
from flask_babel import _

COMMAND_NAME = "ping"
COMMAND_DESC = "Botun çalışıp çalışmadığını kontrol eder."

async def handler(event):
    """Handles the !ping command."""
    try:
        print(f"Received !{COMMAND_NAME} command. Responding...")
        start_time = datetime.now()
        # Send a message and wait for it to be sent
        message = await event.edit(_("Pong!"))
        end_time = datetime.now()
        # Calculate the difference (latency)
        latency = (end_time - start_time).total_seconds() * 1000 # Convert to milliseconds
        # Edit the message to include the latency
        await message.edit(_("Pong! Latency: {ms:.2f} ms").format(ms=latency))
        print("Pong response sent.")
    except Exception as e:
        print(f"Error handling !{COMMAND_NAME}: {e}")

def register(client, me_id, account_id):
    """Registers the command handler with the client."""
    client.add_event_handler(
        handler,
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}$')
    )
    print(f"--- Registering '!{COMMAND_NAME}' for account {account_id}")
    print(f"Command '!{COMMAND_NAME}' registered.") 