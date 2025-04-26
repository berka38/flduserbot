from telethon import events
import wikipedia
from flask_babel import _, get_locale

COMMAND_NAME = "wiki"
COMMAND_DESC = _("Searches Wikipedia for a summary of the given topic. Usage: !wiki <topic>")

async def handler(event):
    """Handles the !wiki command."""
    query = event.pattern_match.group(1)
    if not query:
        await event.edit(_("Please provide a topic to search for. Usage: `!wiki <topic>`"))
        return

    try:
        # Try to set Wikipedia language based on Flask-Babel locale
        lang = str(get_locale()) if get_locale() else 'en' # Default to English
        if '_' in lang: # Handle locales like en_US
            lang = lang.split('_')[0]
        try:
            wikipedia.set_lang(lang)
        except wikipedia.exceptions.WikipediaException as lang_err:
             print(f"[Wiki Command] Warning: Could not set language to '{lang}', falling back to 'en'. Error: {lang_err}")
             wikipedia.set_lang('en') # Fallback to English if locale code is invalid

        await event.edit(_("Searching Wikipedia for '{query}'...").format(query=query))
        
        # Get summary (handle disambiguation and page not found)
        try:
            summary = wikipedia.summary(query, sentences=3) # Get first 3 sentences
            page = wikipedia.page(query) # Get the full page object for the URL
            response_text = f"**Wikipedia Summary for '{query}':**\n\n"
            response_text += f"{summary}\n\n"
            response_text += f"**Read more:** {page.url}"
            await event.edit(response_text)
            
        except wikipedia.exceptions.PageError:
             await event.edit(_("Sorry, I couldn't find a Wikipedia page for '{query}'.").format(query=query))
        except wikipedia.exceptions.DisambiguationError as e:
             options = "\n - ".join(e.options[:5]) # Show first 5 options
             await event.edit(_("''{query}'' could refer to multiple topics. Please be more specific. Options include:\n - {options}").format(query=query, options=options))
        
    except Exception as e:
        await event.edit(_("An error occurred while searching Wikipedia: {error}").format(error=str(e)))
        print(f"Error handling !{COMMAND_NAME}: {e}")

def register(client, me_id, account_id):
    """Registers the command handler with the client."""
    # Pattern allows for spaces in the query
    client.add_event_handler(
        handler,
        events.NewMessage(from_users=me_id, pattern=rf'^!{COMMAND_NAME}\s+(.+)$')
    )
    print(f"Command '!{COMMAND_NAME}' registered for account {account_id}.") 