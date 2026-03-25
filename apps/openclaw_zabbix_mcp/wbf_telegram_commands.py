from telegram import Update
from telegram.ext import ContextTypes

from wbf_assistant import (
    WarsawBeerFestivalAssistant,
    format_beer,
    format_serving_options,
)

assistant = WarsawBeerFestivalAssistant()


def _args(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args or []).strip()


def _parse_fun_beer_filters(query: str) -> dict:
    q = (query or "").strip().lower()

    style = None
    budget = None
    package = None
    size = None
    brewery = None
    min_abv = None
    max_abv = None
    limit = 15
    sort_mode = None
    text_search = None
    after_id = None

    import re

    style_candidates = [
        "imperial stout",
        "non alcoholic",
        "alcohol free",
        "grodziskie",
        "hefeweizen",
        "berliner weisse",
        "pastry sour",
        "pale ale",
        "pilsner",
        "lager",
        "stout",
        "porter",
        "sour",
        "gose",
        "cider",
        "mead",
        "neipa",
        "ddh",
        "ipa",
        "pils",
        "wheat",
        "weizen",
        "saison",
        "tripel",
        "dubbel",
        "lambic",
        "wild",
        "kvass",
    ]
    for candidate in style_candidates:
        if candidate in q:
            style = candidate
            break

    m = re.search(r'\bmax\s+(\d+(?:[.,]\d+)?)\b', q)
    if m:
        budget = float(m.group(1).replace(",", "."))

    m = re.search(r'\bunder\s+(\d+(?:[.,]\d+)?)\s*(?:zl|zł|pln)?\b', q)
    if m:
        budget = float(m.group(1).replace(",", "."))

    m = re.search(r'\bmin\s+(\d+(?:[.,]\d+)?)\s*(?:abv|%)?\b', q)
    if m:
        min_abv = float(m.group(1).replace(",", "."))

    m = re.search(r'\bmaxabv\s+(\d+(?:[.,]\d+)?)\b', q)
    if m:
        max_abv = float(m.group(1).replace(",", "."))

    m = re.search(r'--min-abv\s+(\d+(?:[.,]\d+)?)', q)
    if m:
        min_abv = float(m.group(1).replace(",", "."))

    m = re.search(r'--max-abv\s+(\d+(?:[.,]\d+)?)', q)
    if m:
        max_abv = float(m.group(1).replace(",", "."))

    m = re.search(r'--after-id\s+(\d+)', q)
    if m:
        after_id = int(m.group(1))

    m = re.search(r'\brandom\s+(\d+)\b', q)
    if m:
        limit = max(1, min(20, int(m.group(1))))

    if "draft" in q:
        package = "draft"
    elif "can" in q:
        package = "can"
    elif "bottle" in q:
        package = "bottle"

    for candidate in ["100ml", "150ml", "200ml", "300ml", "330ml", "500ml", "750ml", "0.5l"]:
        if candidate in q:
            size = candidate
            break

    m = re.search(r'\bbrewery\s+"([^"]+)"', query, flags=re.IGNORECASE)
    if m:
        brewery = m.group(1).strip()
    else:
        m = re.search(r'\bbrewery\s+([a-zA-Z0-9ąćęłńóśżźĄĆĘŁŃÓŚŻŹ\-\s]+?)(?:\s+(?:min|max|cheap|expensive|draft|can|bottle|style|text)\b|$)', query, flags=re.IGNORECASE)
        if m:
            brewery = m.group(1).strip()

    m = re.search(r'\btext\s+"([^"]+)"', query, flags=re.IGNORECASE)
    if m:
        text_search = m.group(1).strip()

    if "cheap" in q:
        sort_mode = "cheap"
    elif "expensive" in q:
        sort_mode = "expensive"
    elif "strong" in q:
        sort_mode = "strong"

    return {
        "style": style,
        "budget": budget,
        "package": package,
        "size": size,
        "brewery": brewery,
        "min_abv": min_abv,
        "max_abv": max_abv,
        "limit": limit,
        "sort_mode": sort_mode,
        "text_search": text_search,
        "after_id": after_id,
    }


async def next_beer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    beer = assistant.recommend_beer(update.effective_chat.id, query=query)
    if not beer:
        await update.message.reply_text("No matching beer found.")
        return
    await update.message.reply_text(format_beer(beer))


async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    beer = assistant.recommend_beer(update.effective_chat.id, query=query)
    if not beer:
        await update.message.reply_text("No recommendation found.")
        return
    await update.message.reply_text(format_beer(beer))


async def random_beer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)

    parsed = _parse_fun_beer_filters(query)
    beers = assistant.random_beers(query=query, limit=parsed["limit"])

    if not beers:
        await update.message.reply_text("No random beer available.")
        return

    lines = [f"🎲 Random beers ({len(beers)}):"]
    for beer in beers:
        price = beer.get("cheapest_price_pln")
        if price is None:
            price_txt = "n/a"
        else:
            eur = beer.get("cheapest_price_eur")
            if eur is not None:
                price_txt = f"{price:.2f} PLN ({eur:.2f} EUR)"
            else:
                price_txt = f"{price:.2f} PLN"

        lines.append(
            f"- #{beer.get('id')} {beer.get('name')} | "
            f"{beer.get('brewery') or 'n/a'} | "
            f"{beer.get('style') or 'n/a'} | "
            f"ABV={beer.get('abv') or 'n/a'} | "
            f"{price_txt}"
        )

    await update.message.reply_text("\n".join(lines))


async def drank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    name = _args(context)
    if not name:
        await update.message.reply_text("Usage: /drank <beer name>")
        return

    beer = assistant.mark_drank(update.effective_chat.id, name)
    if not beer:
        await update.message.reply_text("Beer not found.")
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
        await update.message.reply_text("Rating must be 1-5.")
        return

    if rating < 1 or rating > 5:
        await update.message.reply_text("Rating must be 1-5.")
        return

    beer_name = " ".join(args[:-1]).strip()
    beer = assistant.rate_beer(update.effective_chat.id, beer_name, rating)
    if not beer:
        await update.message.reply_text("Beer not found.")
        return

    await update.message.reply_text(f"Rated {beer.get('name')} as {rating}/5")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    rows = assistant.history(update.effective_chat.id)
    if not rows:
        await update.message.reply_text("No beer history yet.")
        return

    lines = ["Your history:"]
    for row in rows[:20]:
        lines.append(
            f"- {row.get('drank_at', '')[:19]} | {row.get('name')} | "
            f"{row.get('brewery') or 'n/a'} | rating={row.get('rating') or 'n/a'}"
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
        await update.message.reply_text("ABV must be numeric.")
        return

    profile = assistant.set_max_abv(update.effective_chat.id, max_abv)
    await update.message.reply_text(f"Max ABV updated to {profile['max_abv']}")


async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = _args(context)
    if not location:
        await update.message.reply_text("Usage: /set_location <location>")
        return

    profile = assistant.set_location(update.effective_chat.id, location)
    await update.message.reply_text(f"Current location set to: {profile.get('current_location') or 'n/a'}")


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
    for beer in beers[:10]:
        price = beer.get("cheapest_price_pln")
        if price is None:
            price_txt = "n/a"
        else:
            eur = beer.get("cheapest_price_eur")
            if eur is not None:
                price_txt = f"{price:.2f} PLN ({eur:.2f} EUR)"
            else:
                price_txt = f"{price:.2f} PLN"

        lines.append(
            f"- #{beer.get('id')} {beer.get('name')} | {beer.get('brewery') or 'n/a'} | "
            f"{beer.get('style') or 'n/a'} | ABV={beer.get('abv') or 'n/a'} | {price_txt}"
        )

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
    for brewery in breweries[:10]:
        cheap = brewery.get("cheapest_beer_pln")
        cheap_txt = f"{cheap:.2f} PLN" if cheap is not None else "n/a"
        lines.append(
            f"- {brewery.get('name')} | beers={brewery.get('beers')} | cheapest={cheap_txt}"
        )

    await update.message.reply_text("\n".join(lines))


async def cheap_beers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    parsed = _parse_fun_beer_filters(query)

    beers = assistant.cheapest_beers(
        style=parsed["style"],
        budget=parsed["budget"],
        package=parsed["package"],
        size=parsed["size"],
        limit=min(parsed["limit"], 15),
    )
    if not beers:
        await update.message.reply_text("No cheap beers found.")
        return

    lines = ["💸 Cheapest beers:"]
    for beer in beers:
        price = beer.get("cheapest_price_pln")
        eur = beer.get("cheapest_price_eur")

        if price is not None and eur is not None:
            price_txt = f"{price:.2f} PLN ({eur:.2f} EUR)"
        elif price is not None:
            price_txt = f"{price:.2f} PLN"
        else:
            price_txt = "n/a"

        lines.append(
            f"- #{beer.get('id')} {beer.get('name')} | {beer.get('brewery')} | "
            f"{beer.get('style') or 'n/a'} | ABV={beer.get('abv') or 'n/a'} | {price_txt}"
        )

    await update.message.reply_text("\n".join(lines))


async def serving_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    if not query:
        await update.message.reply_text("Usage: /serving_options <beer name>")
        return

    beer, options = assistant.serving_options(query)
    if not beer:
        await update.message.reply_text("Beer not found.")
        return

    await update.message.reply_text(format_serving_options(beer, options))


async def brewery_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistant.ensure_data_loaded()
    query = _args(context)
    if not query:
        await update.message.reply_text("Usage: /brewery_map <brewery name>")
        return

    links = assistant.brewery_map_links(query)
    if not links:
        await update.message.reply_text("No map links available.")
        return

    msg = (
        f"🗺 Brewery map links for: {query}\n"
        f"Google Maps: {links['google_maps']}\n"
        f"OpenStreetMap: {links['openstreetmap']}"
    )
    await update.message.reply_text(msg)
