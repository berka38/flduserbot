from telethon import events
import random
from flask_babel import _

COMMAND_NAME = "rps"
COMMAND_DESC = "Taş-Kağıt-Makas oyunu. Kullanım: !rps <taş|kağıt|makas>"

OPTIONS = ["taş", "kağıt", "makas"]
EMOJIS = {"taş": "🗿", "kağıt": "📄", "makas": "✂️"}

async def handler(event):
    """Handles the !rps command."""
    try:
        user_choice = event.pattern_match.group(1)
        if not user_choice or user_choice.lower() not in OPTIONS:
            await event.edit(f"Geçersiz seçim. Kullanım: `!{COMMAND_NAME} <taş|kağıt|makas>`")
            return
            
        user_choice = user_choice.lower()
        bot_choice = random.choice(OPTIONS)
        
        result_msg = f"Senin seçimin: {EMOJIS[user_choice]} {user_choice.capitalize()}\n"
        result_msg += f"Botun seçimi: {EMOJIS[bot_choice]} {bot_choice.capitalize()}\n\n"
        
        if user_choice == bot_choice:
            result_msg += "**Sonuç: Berabere!** 🤷‍♂️"
        elif (user_choice == "taş" and bot_choice == "makas") or \
             (user_choice == "kağıt" and bot_choice == "taş") or \
             (user_choice == "makas" and bot_choice == "kağıt"):
            result_msg += "**Sonuç: Kazandın!** 🎉"
        else:
            result_msg += "**Sonuç: Kaybettin!** 😭"
            
        await event.edit(result_msg)
        
    except Exception as e:
        await event.edit(f"Hata: {e}")
        print(f"Error handling !{COMMAND_NAME}: {e}")

def register(client, me_id, account_id):
    """Registers the command handler with the client."""
    # Pattern'ı argüman alacak şekilde güncelleyelim
    client.add_event_handler(
        handler,
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}\s*(.*)$')
    )
    print(f"Command '!{COMMAND_NAME}' registered.") 