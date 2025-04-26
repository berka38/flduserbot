from telethon import events
from telethon.tl.types import ChannelParticipantsAdmins
from flask_babel import _

COMMAND_NAME = "admins"
COMMAND_DESC = "Mevcut sohbetteki yöneticileri listeler."

async def handler(event):
    """Handles the !admins command."""
    try:
        chat = await event.get_chat()
        if not hasattr(chat, 'admin_rights'): # Sadece grup/kanal benzeri yerlerde çalışır
            await event.edit("Bu komut sadece gruplarda veya kanallarda kullanılabilir.")
            return

        admins = []
        async for user in event.client.iter_participants(chat, filter=ChannelParticipantsAdmins):
            name = user.first_name
            if user.last_name:
                name += f" {user.last_name}"
            username = f" (@{user.username})" if user.username else ""
            admins.append(f"- [{name}](tg://user?id={user.id}){username}")
        
        if not admins:
            await event.edit("Bu sohbette yönetici bulunamadı veya listeleme yetkim yok.")
            return
            
        admin_list = "\n".join(admins)
        await event.edit(f"**Sohbet Yöneticileri:**\n\n{admin_list}", parse_mode='md')

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