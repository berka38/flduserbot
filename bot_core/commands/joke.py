from telethon import events
import random
from flask_babel import _

COMMAND_NAME = "espri"
COMMAND_DESC = "Rastgele bir espri yapar."

JOKES = [
    "Adamın biri varmış, ikinci dönem düzeltmiş.",
    "Yıkanan Ton balığına ne denir? Washington.",
    "Sinemada on dakika ara dedi, aradım aradım açmadı.",
    "Ben ekmek yedim, DiCaprio.",
    "Temel Fransa'ya gitmiş. Bir Fransız Temel'e sormuş: 'Quelle heure est-il?' Temel cevap vermiş: 'Kel horoz itilmez, o zaten kendiliğinden düşer!'",
    "Uzun lafın kısası: U.L.",
    "Adamın biri güneşte yanmış, ayda düz.",
    "Çalmadığım kapı kalmadı." "O zaman bir de kilitlemeyi dene.",
    "Espriliyim ama bazen şaka yapıyorum."
]

async def handler(event):
    """Handles the !espri command."""
    try:
        joke = random.choice(JOKES)
        await event.edit(f"😂 İşte espri:\n\n{joke}")
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