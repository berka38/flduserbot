from telethon import events
from telethon.tl.functions.messages import UpdatePinnedMessageRequest
from telethon.errors import ChatAdminRequiredError
from flask_babel import _

COMMAND_NAME = "pin"
COMMAND_DESC = "Yanıt verilen mesajı sohbete sabitler (Admin yetkisi gerekir)."

async def handler(event):
    """Handles the !pin command."""
    if not event.is_group and not event.is_channel:
        await event.edit("Bu komut sadece gruplarda veya kanallarda kullanılabilir.")
        return
        
    if not event.reply_to_msg_id:
        await event.edit("Lütfen sabitlemek istediğiniz mesaja yanıt verin.")
        return

    # Yönetici mi kontrol et (basit kontrol)
    chat = await event.get_chat()
    sender = await event.get_sender()
    # Hem gönderenin hem de botun pin yetkisi olmalı
    can_pin = False
    try:
        me = await event.client.get_me()
        me_perms = await event.client.get_permissions(chat, me)
        if me_perms.is_admin and me_perms.admin_rights.pin_messages:
            can_pin = True
        # Kullanıcının kendi yetkisini de kontrol etmek isteyebiliriz ama şimdilik botun yetkisi yeterli
        # sender_perms = await event.client.get_permissions(chat, sender)
        # if sender_perms.is_admin and sender_perms.admin_rights.pin_messages and me_perms.is_admin and me_perms.admin_rights.pin_messages:
        #    can_pin = True
            
    except Exception as e:
        print(f"Error checking pin permissions: {e}")
        # Yetki kontrolünde hata olursa yine de denemeye çalışabiliriz, Telegram API hatayı verir.
        can_pin = True # Hata durumunda denemeye izin verelim
        
    if not can_pin:
         await event.edit("Mesaj sabitlemek için yönetici yetkim yok.")
         return

    try:
        await event.edit("Mesaj sabitleniyor...")
        await event.client(UpdatePinnedMessageRequest(
            peer=chat,
            id=event.reply_to_msg_id,
            # silent=True # İsteğe bağlı: Bildirim gönderme
        ))
        await event.edit("Mesaj başarıyla sabitlendi.")
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