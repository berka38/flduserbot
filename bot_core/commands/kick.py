from telethon import events
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights
import time
from telethon.errors.rpcerrorlist import UserAdminInvalidError, ChatAdminRequiredError
from flask_babel import _

COMMAND_NAME = "kick"
COMMAND_DESC = "Bir kullanıcıyı gruptan atar (Admin yetkisi gerekir). Kullanım: !kick <kullanıcı_adı/@id/mesaja_yanıt>"

async def handler(event):
    """Handles the !kick command."""
    if not event.is_group:
        await event.edit("Bu komut sadece gruplarda kullanılabilir.")
        return

    # Yönetici mi kontrol et (basit kontrol, tüm hakları kontrol etmez)
    chat = await event.get_chat()
    sender = await event.get_sender()
    if not sender or not hasattr(sender, 'admin_rights') or not sender.admin_rights.ban_users:
        # Kendimizin (bot hesabının) yetkisi var mı?
        me = await event.client.get_me()
        try:
            participant = await event.client.get_permissions(chat, me)
            if not participant.is_admin or not participant.admin_rights.ban_users:
                 await event.edit("Birini atmak için yönetici yetkim yok.")
                 return
        except Exception:
            await event.edit("Yönetici yetkimi kontrol ederken hata oluştu.")
            return

    target_user = None
    reason = "".join(event.text.split(maxsplit=1)[1:]) # Argümanı al

    # Hedefi belirle (yanıt veya argüman)
    if event.reply_to_msg_id and not reason:
        reply_message = await event.get_reply_message()
        if reply_message and reply_message.sender_id:
            target_user = await event.client.get_entity(reply_message.sender_id)
    elif reason:
        try:
            target_user = await event.client.get_entity(reason)
        except ValueError: # Kullanıcı adı/ID bulunamadı
            pass # Hata mesajı aşağıda verilecek

    if not target_user:
        await event.edit(f"Kullanıcı bulunamadı. Kullanım: `!{COMMAND_NAME} <kullanıcı_adı/@id/mesaja_yanıt>`")
        return
        
    # Kendini veya başka bir admini atmayı engelle (basit kontrol)
    if target_user.id == (await event.client.get_me()).id:
        await event.edit("Kendimi atamam.")
        return
    try:
        target_participant = await event.client.get_permissions(chat, target_user)
        if target_participant and (target_participant.is_admin or target_participant.is_creator):
            await event.edit("Yöneticileri veya kurucuyu atamam.")
            return
    except Exception:
        pass # Kullanıcı grupta değilse veya hata olursa devam et

    try:
        await event.edit(f"`{target_user.first_name}` gruptan atılıyor...")
        # kick için EditBannedRequest kullanılır
        await event.client(EditBannedRequest(channel=chat, participant=target_user, banned_rights=ChatBannedRights(until_date=None, view_messages=True)))
        # Kullanıcıyı tekrar eklemek için hakları sıfırla (kick etkisi)
        await asyncio.sleep(1) # Hemen yapınca bazen çalışmıyor
        await event.client(EditBannedRequest(channel=chat, participant=target_user, banned_rights=ChatBannedRights(until_date=None)))
        await event.edit(f"✅ `{target_user.first_name}` başarıyla gruptan atıldı.")
        # İsteğe bağlı: Komut mesajını sil
        # await asyncio.sleep(5)
        # await event.delete()

    except Exception as e:
        await event.edit(f"Hata: {e}")
        print(f"Error handling !{COMMAND_NAME}: {e}")

def register(client, me_id, account_id):
    """Registers the command handler with the client."""
    client.add_event_handler(
        handler,
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}(?:\s+(.*)|$)')
    )
    print(f"Command '!{COMMAND_NAME}' registered.") 