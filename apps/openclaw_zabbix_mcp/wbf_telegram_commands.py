from telegram import Update
from telegram.ext import ContextTypes

from wbf_assistant import WarsawBeerFestivalAssistant, format_beer, format_event

assistant = WarsawBeerFestivalAssistant()


def _args(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args or []).strip()


async def next_beer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    beer = assistant.recommend_beer(update.effective_chat.id)
    if not beer:
        await update.message.reply_text("No matching beer found in imported data.")
        return
    await update.message.reply_text(format_beer(beer))


async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    beer = assistant.recommend_beer(update.effective_chat.id, query=query)
    if not beer:
        await update.message.reply_text("No recommendation found for your filters/history.")
        return
    await update.message.reply_text(format_beer(beer))


async def drank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    name = _args(context)
    if not name:
        await update.message.reply_text("Usage: /drank <beer name>")
        return
    beer = assistant.mark_drank(update.effective_chat.id, name)
    if not beer:
        await update.message.reply_text("Beer not found in structured data.")
        return
    await update.message.reply_text(f"Logged as drank:\n{format_beer(beer)}")


async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /rate <beer name> <1-5>")
        return
    try:
        rating = int(args[-1])
    except ValueError:
        await update.message.reply_text("Rating must be a number from 1 to 5.")
        return
    if rating < 1 or rating > 5:
        await update.message.reply_text("Rating must be 1-5.")
        return
    name = " ".join(args[:-1]).strip()
    beer = assistant.rate_beer(update.effective_chat.id, name, rating)
    if not beer:
        await update.message.reply_text("Beer not found in structured data.")
        return
    await update.message.reply_text(f"Rated {beer.get('name')} as {rating}/5")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    rows = assistant.history(update.effective_chat.id)
    if not rows:
        await update.message.reply_text("No beer history yet. Use /drank or /rate first.")
        return
    lines = ["Your history:"]
    for row in rows[:20]:
        lines.append(
            f"- {row.get('drank_at')[:19]} | {row.get('name')} ({row.get('brewery') or 'n/a'}) rating={row.get('rating') or 'n/a'}"
        )
    await update.message.reply_text("\n".join(lines))


async def set_max_abv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = _args(context)
    if not value:
        await update.message.reply_text("Usage: /set_max_abv <value>")
        return
    try:
        max_abv = float(value)
    except ValueError:
        await update.message.reply_text("ABV must be numeric, e.g. 6.5")
        return
    profile = assistant.set_max_abv(update.effective_chat.id, max_abv)
    await update.message.reply_text(f"Max ABV updated to {profile['max_abv']}")


async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = _args(context)
    if not location:
        await update.message.reply_text("Usage: /set_location <zone>")
        return
    profile = assistant.set_location(update.effective_chat.id, location)
    await update.message.reply_text(f"Current location set to: {profile.get('current_location') or 'n/a'}")


async def next_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    event = assistant.next_event()
    await update.message.reply_text(format_event(event))


async def events_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    events = assistant.events_today()
    if not events:
        await update.message.reply_text("No events found for today in imported schedule.")
        return
    lines = ["Today's events:"]
    for event in events:
        lines.append(f"- {event.get('start_ts') or 'n/a'} | {event.get('title')}")
    await update.message.reply_text("\n".join(lines))


async def beer_and_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    beer, event = assistant.beer_and_event(update.effective_chat.id, query)
    message = f"{format_beer(beer)}\n\n{format_event(event)}"
    await update.message.reply_text(message)


async def random_beer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    beer = assistant.recommend_beer(update.effective_chat.id, random_mode=True)
    if not beer:
        await update.message.reply_text("No random beer available with current filters.")
        return
    await update.message.reply_text(format_beer(beer))


async def find_beer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    if not query:
        await update.message.reply_text("Usage: /find_beer <name>")
        return
    beers = assistant.find_beers(query)
    if not beers:
        await update.message.reply_text("No beers found.")
        return
    lines = ["Found beers:"]
    for beer in beers:
        lines.append(f"- {beer.get('name')} | {beer.get('brewery') or 'n/a'} | ABV={beer.get('abv') or 'n/a'}")
    await update.message.reply_text("\n".join(lines))


async def find_brewery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    if not query:
        await update.message.reply_text("Usage: /find_brewery <name>")
        return
    breweries = assistant.find_breweries(query)
    if not breweries:
        await update.message.reply_text("No breweries found.")
        return
    lines = ["Found breweries:"]
    for brewery in breweries:
        lines.append(
            f"- {brewery.get('name')} | beers={brewery.get('beers')} | zone={brewery.get('zone') or 'n/a'} stand={brewery.get('stand') or 'n/a'}"
        )
    await update.message.reply_text("\n".join(lines))
