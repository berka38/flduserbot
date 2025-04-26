from telethon import events
from flask_babel import _

COMMAND_NAME = "id"
COMMAND_DESC = "Sizin ve mevcut sohbetin ID'lerini gösterir."

async def handler(event):
    """Handles the !id command."""
    try:
        chat_id = event.chat_id
        user_id = event.sender_id
        reply_msg = f"**Sizin ID'niz:** `{user_id}`\n"
        reply_msg += f"**Bu Sohbet ID'si:** `{chat_id}`"
        
        # Eğer bir mesaja yanıt olarak kullanılırsa, o mesajın ve sahibinin ID'sini de ekle
        if event.reply_to_msg_id:
            reply_message = await event.get_reply_message()
            if reply_message:
                reply_msg += f"\n**Yanıtlanan Mesaj ID:** `{reply_message.id}`"
                if reply_message.sender_id:
                     reply_msg += f"\n**Yanıtlanan Kullanıcı ID:** `{reply_message.sender_id}`"
            
        await event.edit(reply_msg)
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