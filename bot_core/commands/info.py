from telethon import events
from flask_babel import _

COMMAND_NAME = "info"
COMMAND_DESC = "Mevcut sohbetin veya yanıtlanan kullanıcının temel bilgilerini gösterir."

async def handler(event):
    """Handles the !info command."""
    try:
        target_entity = None
        info_msg = "**Bilgi:**\n\n"
        
        if event.reply_to_msg_id:
            reply_message = await event.get_reply_message()
            if reply_message and reply_message.sender_id:
                try:
                    target_entity = await event.client.get_entity(reply_message.sender_id)
                    info_msg += f"__Kullanıcı Bilgisi (Yanıtlanan):__\n"
                except Exception:
                    info_msg += "Yanıtlanan kullanıcı bilgisi alınamadı.\n"
        
        if not target_entity:
            target_entity = await event.get_chat()
            info_msg += "__Sohbet Bilgisi:__\n"
            
        if target_entity:
            info_msg += f"**ID:** `{target_entity.id}`\n"
            if hasattr(target_entity, 'title'): # Grup/Kanal
                info_msg += f"**Başlık:** {target_entity.title}\n"
            if hasattr(target_entity, 'username') and target_entity.username:
                info_msg += f"**Kullanıcı Adı:** @{target_entity.username}\n"
            if hasattr(target_entity, 'first_name'): # Kullanıcı
                name = target_entity.first_name
                if hasattr(target_entity, 'last_name') and target_entity.last_name:
                    name += f" {target_entity.last_name}"
                info_msg += f"**İsim:** {name}\n"
            if hasattr(target_entity, 'is_bot') and target_entity.is_bot:
                 info_msg += f"**Bot:** Evet\n"
            # Daha fazla bilgi eklenebilir (örn: DC ID, Scammed, etc.)
        else:
            info_msg = "Bilgi alınacak sohbet veya kullanıcı bulunamadı."
            
        await event.edit(info_msg)
        
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