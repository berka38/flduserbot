from telethon import events
from telethon.tl.types import ChannelParticipantsAdmins
import asyncio
from flask_babel import _

COMMAND_NAME = "tagall"
COMMAND_DESC = "Mevcut gruptaki tüm üyeleri etiketler (Dikkatli kullanın!). Kullanım: !tagall <mesaj> <gecikme_sn>"

# Global tagging_active sözlüğünü tanımlıyoruz.
tagging_active = {}

async def handler(event):
    """Handles the !tagall command."""
    global tagging_active

    if not event.is_group:
        await event.edit("Bu komut sadece gruplarda kullanılabilir.")
        return
    
    # Argüman sayısını kontrol ediyoruz.
    args = event.text.split(maxsplit=2)
    if len(args) < 3:
        await event.edit("Kullanım: !tagall <mesaj> <gecikme_sn>")
        return

    # Komut mesajını sil
    await event.delete()
        
    try:
        # Kullanıcıları al
        participants = await event.client.get_participants(event.chat_id)
        
        # Mesaj ve zaman ayarı: son argüman gecikme süresi, kalanlar mesaj içeriği
        message = ' '.join(args[1:-1])  # Komut adı hariç, son argüman hariç tüm argümanlar mesajı oluşturur.
        time_interval = int(args[-1]) if args[-1].isdigit() else 1  # Varsayılan 1 saniye
        
        # İşlemi başlat
        tagging_active[event.chat_id] = True

        for user in participants:
            if not tagging_active.get(event.chat_id):  # Eğer stop_tag çağrıldıysa dur
                await event.reply("🚫 **Tagging stopped!**")
                return
            
            if user.username:
                await event.reply(f'@{user.username} {message}')
            else:
                await event.reply(f'[{user.first_name}](tg://user?id={user.id}) {message}')
            
            await asyncio.sleep(time_interval)  # Bekleme süresi
        
        return {
            "prefix": "tag",
            "return": "✅ **Users tagged successfully.**"
        }
    except Exception as e:
        return {
            "prefix": "tag",
            "return": f"⚠️ **Error:** {str(e)}"
        }

def register(client, me_id, account_id):
    """Registers the command handler with the client."""
    client.add_event_handler(
        handler,
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}(?:\s+(.*))?$') 
    )
    print(f"Command '!{COMMAND_NAME}' registered.")
