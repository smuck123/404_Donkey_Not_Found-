import logging
import re
import random as _random

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from config import BOT_TOKEN, validate_config, FIREWALL_HOST
from chat_registry import register_chat, list_chats
from daily_report import build_daily_report
from zabbix_ai import (
    chat_with_ai,
    normalize_host,
    get_problems,
    get_summary,
    search_hosts,
    get_host_status,
    summarize_traffic_with_ai,
    get_cpu_load_text,
    summarize_host_24h_with_ai,
    summarize_gpu_with_ai,
)
from fortigate_ai import (
    summarize_fortigate_snapshot,
    explain_fortigate_api_capabilities,
    build_block_ip_plan,
    build_site_to_site_vpn_plan,
    summarize_fortigate_traffic,
    show_top_talkers,
    show_blocked_ips,
    bot_capabilities_text,
    approve_block_ip,
    approve_site_to_site_vpn,
)
from wbf_telegram_commands import (
    next_beer,
    recommend,
    drank,
    rate,
    history,
    set_max_abv,
    set_location,
    random_beer,
    find_beer,
    find_brewery,
    cheap_beers,
    serving_options,
    brewery_map,
)
from wbf_assistant import (
    WarsawBeerFestivalAssistant,
    format_beer,
    format_serving_options,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
LOG = logging.getLogger(__name__)

wbf_ai = WarsawBeerFestivalAssistant()

BEER_STYLE_WORDS = [
    "ipa", "neipa", "ddh", "lager", "stout", "porter", "sour", "gose",
    "pils", "pilsner", "pale ale", "weizen", "wheat", "pastry",
    "mead", "cider", "grodziskie", "schwarzbier", "non alcoholic",
]

BEER_TRIGGER_WORDS = [
    "beer", "beers", "brewery", "brew", "festival beer", "next beer",
    "what should i drink", "what beer", "find beer", "find brewery",
    "drink next", "cheap beers", "budget beers", "serving options",
    "map for brewery", "drunk donkey", "beer senior analyzer",
    "beer help", "help beer", "beers help",
]

PACKAGE_WORDS = ["can", "draft", "bottle"]


def _looks_like_beer_request(text: str) -> bool:
    t = (text or "").lower().strip()
    if t in ["beer", "beers", "beer help", "help beer", "beers help"]:
        return True
    if any(word in t for word in BEER_TRIGGER_WORDS):
        return True
    if any(word in t for word in BEER_STYLE_WORDS):
        return True
    if t.startswith("beer "):
        return True
    return False


def _looks_like_fun_beer_query(text: str) -> bool:
    t = (text or "").lower().strip()
    return t == "beer" or t.startswith("beer ")


def _extract_number(text: str, flag: str) -> float | None:
    m = re.search(rf"{re.escape(flag)}\s+(\d+(?:[.,]\d+)?)", text, re.I)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _extract_int_flag(text: str, flag: str) -> int | None:
    m = re.search(rf"{re.escape(flag)}\s+(\d+)", text, re.I)
    if not m:
        return None
    return int(m.group(1))


def _extract_quoted(text: str, label: str) -> str | None:
    m = re.search(rf'{re.escape(label)}\s+"([^"]+)"', text, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(rf"{re.escape(label)}\s+'([^']+)'", text, re.I)
    if m:
        return m.group(1).strip()
    return None


def _extract_style(text: str) -> str | None:
    m = re.search(r'--style\s+([a-zA-Z0-9\-\s]+)', text, re.I)
    if m:
        return m.group(1).strip().lower()

    m = re.search(r'\bstyle\s+"([^"]+)"', text, re.I)
    if m:
        return m.group(1).strip().lower()

    m = re.search(r"\bstyle\s+'([^']+)'", text, re.I)
    if m:
        return m.group(1).strip().lower()

    m = re.search(
        r"\bstyle\s+([a-zA-Z0-9\-\s]+?)(?:\s+(?:max|min|cheap|cheapest|expensive|draft|can|bottle|brewery|text|random|--[a-z\-]+)\b|$)",
        text,
        re.I,
    )
    if m:
        value = m.group(1).strip().lower()
        if value:
            return value

    lowered = text.lower()
    for word in sorted(BEER_STYLE_WORDS, key=len, reverse=True):
        if word in lowered:
            return word
    return None


def _extract_brewery(text: str) -> str | None:
    m = re.search(r'\bbrewery\s+"([^"]+)"', text, re.I)
    if m:
        return m.group(1).strip()

    m = re.search(r"\bbrewery\s+'([^']+)'", text, re.I)
    if m:
        return m.group(1).strip()

    m = re.search(
        r"\bbrewery\s+([a-zA-Z0-9ąćęłńóśżźĄĆĘŁŃÓŚŻŹ&\-\s]+?)(?:\s+(?:min|max|cheap|cheapest|expensive|draft|can|bottle|text|style|random|--[a-z\-]+)\b|$)",
        text,
        re.I,
    )
    if m:
        return m.group(1).strip()

    return None


def _extract_text_query(text: str) -> str | None:
    q = _extract_quoted(text, "text")
    if q:
        return q
    q = _extract_quoted(text, "beer find text")
    if q:
        return q
    return None


def _extract_package(text: str) -> str | None:
    lowered = text.lower()
    for word in PACKAGE_WORDS:
        if re.search(rf"\b{word}\b", lowered):
            return word
    return None


def _extract_sort(text: str) -> str:
    lowered = text.lower()
    if "cheap" in lowered or "cheapest" in lowered or "budget" in lowered:
        return "cheap"
    if "strong" in lowered or "strongest" in lowered:
        return "strong"
    if "expensive" in lowered:
        return "expensive"
    return "name"


def _format_beer_list(beers: list[dict], title: str) -> str:
    if not beers:
        return f"{title}\n- no results"

    lines = [title]
    for beer in beers[:20]:
        price = beer.get("cheapest_price_pln")
        eur = beer.get("cheapest_price_eur")
        if price is not None and eur is not None:
            price_txt = f"{price:.2f} PLN ({eur:.2f} EUR)"
        elif price is not None:
            price_txt = f"{price:.2f} PLN"
        else:
            price_txt = "n/a"

        lines.append(
            f"- {beer.get('name') or 'n/a'} | "
            f"{beer.get('brewery') or 'n/a'} | "
            f"{beer.get('style') or 'n/a'} | "
            f"ABV={beer.get('abv') or 'n/a'} | "
            f"{price_txt}"
        )
    return "\n".join(lines)


def _format_brewery_list(rows: list[dict], title: str) -> str:
    if not rows:
        return f"{title}\n- no results"

    lines = [title]
    for row in rows[:20]:
        cheap = row.get("cheapest_beer_pln")
        cheap_txt = f"{cheap:.2f} PLN" if cheap is not None else "n/a"
        lines.append(
            f"- {row.get('name') or 'n/a'} | beers={row.get('beers') or 0} | cheapest={cheap_txt}"
        )
    return "\n".join(lines)


def _beer_help_text() -> str:
    return (
        "🍺 Beer mode commands:\n"
        "beer help\n"
        "beer styles\n"
        "beer breweries\n"
        "beer brewery AleBrowar\n"
        "beer cheap style \"IPA\" max 12\n"
        "beer find style ipa\n"
        "beer find style ipa brewery birbant min 7 cheap\n"
        "beer find text \"citra galaxy\"\n"
        "beer next --style ipa --after-id 123\n"
        "beer random 10\n"
        "beer random 8 --min-abv 8\n"
        "\n"
        "Also works:\n"
        "beer\n"
        "help beer\n"
        "cheap beers\n"
        "serving options for Atlantic\n"
        "map for brewery Funky Fluid"
    )


def _full_help_text() -> str:
    return f"{bot_capabilities_text()}\n\n{_beer_help_text()}"


async def _handle_fun_beer_query(update: Update, text_raw: str) -> bool:
    raw = text_raw.strip()
    lower = raw.lower()

    if lower == "beer":
        await _reply(update, _beer_help_text())
        return True

    if not lower.startswith("beer "):
        return False

    cmd = raw[5:].strip()
    cmd_lower = cmd.lower()

    if cmd_lower in ["help", "?", "commands"]:
        await _reply(update, _beer_help_text())
        return True

    if cmd_lower == "styles":
        await _reply(
            update,
            "Beer styles: ipa, neipa, ddh, lager, pils, pilsner, stout, porter, sour, gose, pale ale, wheat, weizen, mead, cider, grodziskie, schwarzbier, non alcoholic"
        )
        return True

    if cmd_lower == "breweries":
        rows = wbf_ai.find_breweries("")
        await _reply(update, _format_brewery_list(rows[:20], "🍻 Breweries (first 20):"))
        return True

    if cmd_lower.startswith("brewery "):
        query = cmd[8:].strip()
        rows = wbf_ai.find_breweries(query)
        await _reply(update, _format_brewery_list(rows, f"🍻 Brewery search: {query}"))
        return True

    if cmd_lower.startswith("find text "):
        text_query = _extract_text_query(f"beer {cmd}")
        if not text_query:
            await _reply(update, "Usage: beer find text \"citra galaxy\"")
            return True
        beers = wbf_ai.repository.list_beers(query=text_query, limit=20)
        await _reply(update, _format_beer_list(beers, f"🔎 Text search: {text_query}"))
        return True

    if cmd_lower.startswith("find"):
        style = _extract_style(cmd)
        brewery = _extract_brewery(cmd)
        min_abv = _extract_number(cmd, "min")
        max_abv = _extract_number(cmd, "max")
        package = _extract_package(cmd)
        sort_by = _extract_sort(cmd)
        text_query = _extract_text_query(cmd) or ""

        beers = wbf_ai.repository.list_beers(
            query=text_query,
            style=style,
            brewery=brewery,
            min_abv=min_abv,
            max_abv=max_abv,
            package=package,
            sort_by=sort_by,
            limit=20,
        )
        await _reply(update, _format_beer_list(beers, "🔎 Beer find:"))
        return True

    if cmd_lower.startswith("cheap"):
        style = _extract_style(cmd)
        max_price = _extract_number(cmd, "max")
        if max_price is None:
            m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", cmd)
            if m:
                max_price = float(m.group(1).replace(",", "."))

        package = _extract_package(cmd)
        beers = wbf_ai.cheapest_beers(
            style=style,
            budget=max_price,
            package=package,
            limit=20,
        )
        await _reply(update, _format_beer_list(beers, "💸 Cheap beers:"))
        return True

    if cmd_lower.startswith("random"):
        parts = cmd.split()
        count = 1
        min_abv = _extract_number(cmd, "--min-abv")
        style = _extract_style(cmd)

        if len(parts) >= 2 and re.fullmatch(r"\d+", parts[1]):
            count = max(1, min(20, int(parts[1])))

        beers = wbf_ai.repository.list_beers(
            style=style,
            min_abv=min_abv,
            limit=300,
        )
        if not beers:
            await _reply(update, "No random beers found.")
            return True

        chosen = beers[:]
        _random.shuffle(chosen)
        chosen = chosen[:count]
        await _reply(update, _format_beer_list(chosen, f"🎲 Random beers ({len(chosen)}):"))
        return True

    if cmd_lower.startswith("next"):
        style = _extract_style(cmd)
        after_id = _extract_int_flag(cmd, "--after-id")

        if after_id is not None:
            beers = wbf_ai.repository.list_beers(style=style, sort_by="name", limit=200)
            beers = [b for b in beers if int(b.get("id", 0) or 0) > after_id]
            if not beers:
                await _reply(update, "No next beer found after that id.")
                return True
            await _reply(update, format_beer(beers[0]))
            return True

        beer = wbf_ai.recommend_beer(update.effective_chat.id, query=cmd)
        if not beer:
            await _reply(update, "No matching beer found.")
            return True

        await _reply(update, format_beer(beer))
        return True

    await _reply(update, _beer_help_text())
    return True


async def _reply(update: Update, text: str):
    if text is None:
        text = ""

    chunk_size = 3500
    parts = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    if not parts:
        parts = [""]

    for part in parts:
        await update.message.reply_text(part)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _reply(update, _full_help_text())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _reply(update, _full_help_text())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_raw = (update.message.text or "").strip()
    text = text_raw.lower()

    chat = update.effective_chat
    user = update.effective_user

    register_chat(
        chat_id=chat.id,
        chat_type=getattr(chat, "type", "") or "",
        title=getattr(chat, "title", "") or "",
        username=getattr(user, "username", "") or "",
        first_name=getattr(user, "first_name", "") or "",
        last_name=getattr(user, "last_name", "") or "",
    )

    try:
        if text in [
            "what can you do",
            "help",
            "commands",
            "bot help",
            "help beer",
            "help beers",
            "beer help",
            "beer commands",
            "hint beer",
            "hint beers",
        ]:
            if "beer" in text or "hint" in text:
                await _reply(update, _beer_help_text())
            else:
                await _reply(update, bot_capabilities_text())
            return

            lines = ["Registered chats:"]
            for c in chats:
                label = c.get("title") or c.get("first_name") or c.get("username") or "unknown"
                lines.append(f"- {c['chat_id']} ({c.get('chat_type', 'unknown')}) {label}")
            await _reply(update, "\n".join(lines))
            return

        if text in ["summarize daily report", "daily report", "daily_report", "show daily report"]:
            report = build_daily_report("TORAKKA")
            await _reply(update, report)
            return

        if text in ["hello", "hi", "hey"]:
            reply = chat_with_ai("Reply with a short friendly greeting.")
            await _reply(update, reply)
            return

        if text.startswith("tell story") or text.startswith("tell me a story"):
            reply = chat_with_ai(text_raw)
            await _reply(update, reply)
            return

        if text.startswith("story about "):
            topic = text_raw[len("story about "):].strip()
            reply = chat_with_ai(f"Tell me a short story about {topic}.")
            await _reply(update, reply)
            return

        if text.startswith("joke") or text.startswith("tell joke"):
            reply = chat_with_ai("Tell a short clean joke.")
            await _reply(update, reply)
            return

        if text.startswith("explain "):
            reply = chat_with_ai(text_raw)
            await _reply(update, reply)
            return

        if text in ["problems", "/problems", "show zabbix problems"]:
            data = get_problems(5)
            if not data:
                await _reply(update, "No problems found.")
                return
            msg = "\n".join([f"- sev={p.get('severity')} {p.get('name')}" for p in data[:5]])
            await _reply(update, msg)
            return

        if text in ["summary", "/summary", "summarize zabbix hosts"]:
            data = get_summary()
            await _reply(update, data.get("summary", str(data)))
            return

        if text.startswith(("search host ", "search hosts ", "/search host ", "find host ")):
            prefixes = ["search host ", "search hosts ", "/search host ", "find host "]
            query = text_raw
            for prefix in prefixes:
                if text.startswith(prefix):
                    query = text_raw[len(prefix):].strip()
                    break
            host = normalize_host(query)
            data = search_hosts(host, 10)
            if not data:
                await _reply(update, f"No hosts found for: {host}")
                return
            msg = "\n".join([f"- {h.get('host')} ({h.get('name')}) status={h.get('status')}" for h in data])
            await _reply(update, msg)
            return

        if text.startswith("get host status for "):
            host = normalize_host(text_raw[len("get host status for "):].strip())
            data = get_host_status(host)
            if not data:
                await _reply(update, "Host not found.")
                return
            h = data[0]
            groups = ", ".join(g.get("name") for g in h.get("groups", []))
            await _reply(update, f"{h.get('host')} status={h.get('status')} groups={groups}")
            return

        if text.startswith("get cpu load for "):
            host = normalize_host(text_raw[len("get cpu load for "):].strip())
            reply = get_cpu_load_text(host)
            await _reply(update, reply)
            return

        if text in ["summarize firewall problems", "analyze firewall", "firewall summary"]:
            reply = summarize_host_24h_with_ai(FIREWALL_HOST)
            await _reply(update, reply)
            return

        if text in ["summarize traffic", "traffic summary", "summarize firewall traffic"]:
            reply = summarize_traffic_with_ai(FIREWALL_HOST)
            await _reply(update, reply)
            return

        if text.startswith("summarize traffic for "):
            host = normalize_host(text_raw[len("summarize traffic for "):].strip())
            reply = summarize_traffic_with_ai(host)
            await _reply(update, reply)
            return

        if text.startswith("summarize host "):
            host = normalize_host(text_raw[len("summarize host "):].strip())
            reply = summarize_host_24h_with_ai(host)
            await _reply(update, reply)
            return

        if text.startswith("summarize problems for "):
            host = normalize_host(text_raw[len("summarize problems for "):].strip())
            reply = summarize_host_24h_with_ai(host)
            await _reply(update, reply)
            return

        if text in ["summarize gpu", "check gpu", "gpu summary"]:
            reply = summarize_gpu_with_ai("TORAKKA")
            await _reply(update, reply)
            return

        if text.startswith("summarize gpu for "):
            host = normalize_host(text_raw[len("summarize gpu for "):].strip())
            reply = summarize_gpu_with_ai(host)
            await _reply(update, reply)
            return

        if text.startswith("check gpu for "):
            host = normalize_host(text_raw[len("check gpu for "):].strip())
            reply = summarize_gpu_with_ai(host)
            await _reply(update, reply)
            return

        if text in ["summarize fortigate", "summarize firewall config", "show fortigate summary"]:
            reply = summarize_fortigate_snapshot()
            await _reply(update, reply)
            return

        if text in ["summarize fortigate traffic", "fortigate traffic summary", "show fortigate traffic"]:
            reply = summarize_fortigate_traffic()
            await _reply(update, reply)
            return

        if text in ["show top talkers", "top talkers", "fortigate top talkers"]:
            reply = show_top_talkers()
            await _reply(update, reply)
            return

        if text in ["show blocked ips", "blocked ips", "show banned ips"]:
            reply = show_blocked_ips()
            await _reply(update, reply)
            return

        if text in ["fortigate api", "what fortigate api can call", "what api can call on fortigate"]:
            reply = explain_fortigate_api_capabilities()
            await _reply(update, reply)
            return

        if text.startswith("plan block ip "):
            ip_address = text_raw[len("plan block ip "):].strip()
            reply = build_block_ip_plan(ip_address)
            await _reply(update, reply)
            return

        if text.startswith("approve block ip "):
            action_id = text_raw[len("approve block ip "):].strip()
            reply = approve_block_ip(action_id)
            await _reply(update, reply)
            return

        if text.startswith("plan site to site vpn "):
            parts = text_raw.split()
            if len(parts) < 8:
                await _reply(
                    update,
                    "Use: plan site to site vpn <peer_ip> <local_subnet> <remote_subnet>"
                )
                return
            peer_ip = parts[5]
            local_subnet = parts[6]
            remote_subnet = parts[7]
            reply = build_site_to_site_vpn_plan(peer_ip, local_subnet, remote_subnet)
            await _reply(update, reply)
            return

        if text.startswith("approve site to site vpn "):
            action_id = text_raw[len("approve site to site vpn "):].strip()
            reply = approve_site_to_site_vpn(action_id)
            await _reply(update, reply)
            return

        if _looks_like_fun_beer_query(text_raw):
            handled = await _handle_fun_beer_query(update, text_raw)
            if handled:
                return

        if _looks_like_beer_request(text):
            counts = wbf_ai.ensure_data_loaded()
            LOG.info("WBF counts: %s", counts)

            if counts.get("beers", 0) == 0:
                await _reply(
                    update,
                    "Beer assistant data is empty. Import failed or no beers were parsed from the source page."
                )
                return

            if text.startswith(("find beer ", "find beers ", "etsi olut", "search beer ")):
                query = text_raw.split(" ", 2)[2].strip()
                beers = wbf_ai.find_beers(query)
                if not beers:
                    await _reply(update, "No beers found.")
                    return
                await _reply(update, _format_beer_list(beers, "Found beers:"))
                return

            if text.startswith(("cheap beers", "cheapest beers", "halpa olut", "halpa bisse", "kipa bisse", "budget beers")):
                beers = wbf_ai.cheapest_beers(limit=15)
                if not beers:
                    await _reply(update, "No cheap beers found.")
                    return
                await _reply(update, _format_beer_list(beers, "💸 Cheapest beers:"))
                return

            if text.startswith("serving options for "):
                beer_name = text_raw[len("serving options for "):].strip()
                beer, options = wbf_ai.serving_options(beer_name)
                if not beer:
                    await _reply(update, "Beer not found.")
                    return
                await _reply(update, format_serving_options(beer, options))
                return

            if text.startswith("map for brewery "):
                brewery_name = text_raw[len("map for brewery "):].strip()
                links = wbf_ai.brewery_map_links(brewery_name)
                if not links:
                    await _reply(update, "No map links available.")
                    return
                await _reply(
                    update,
                    f"🗺 Brewery map links for: {brewery_name}\n"
                    f"Google Maps: {links['google_maps']}\n"
                    f"OpenStreetMap: {links['openstreetmap']}"
                )
                return

            if text.startswith(("find brewery ", "search brewery ")):
                query = text_raw.split(" ", 2)[2].strip()
                breweries = wbf_ai.find_breweries(query)
                if not breweries:
                    await _reply(update, "No breweries found.")
                    return
                await _reply(update, _format_brewery_list(breweries, "Found breweries:"))
                return

            if text.startswith(("i drank ", "drank ")):
                beer_name = text_raw.split(" ", 1)[1].strip()
                beer = wbf_ai.mark_drank(update.effective_chat.id, beer_name)
                if not beer:
                    await _reply(update, "Beer not found in imported data.")
                    return
                await _reply(update, f"Logged as drank:\n{format_beer(beer)}")
                return

            if (
                "recommend" in text
                or "next beer" in text
                or "what should i drink" in text
                or "what beer" in text
                or "drink next" in text
            ):
                beer = wbf_ai.recommend_beer(update.effective_chat.id, query=text_raw)
                if not beer:
                    await _reply(update, "No matching beer found.")
                    return
                await _reply(update, format_beer(beer))
                return

        reply = chat_with_ai(
            f"The user wrote: {text_raw}\n"
            "Reply as a short helpful assistant. "
            "Never explain JSON structure unless the user explicitly asks for parsing or programming help. "
            "If it sounds like monitoring or firewall traffic analysis, keep it operational and concise. "
            "If it is casual chat, answer normally."
        )
        await _reply(update, reply)

    except Exception as e:
        LOG.exception("Telegram router error")
        await _reply(update, f"Error: {e}")


def main():
    validate_config()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("next_beer", next_beer))
    app.add_handler(CommandHandler("recommend", recommend))
    app.add_handler(CommandHandler("drank", drank))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("set_max_abv", set_max_abv))
    app.add_handler(CommandHandler("set_location", set_location))
    app.add_handler(CommandHandler("random_beer", random_beer))
    app.add_handler(CommandHandler("find_beer", find_beer))
    app.add_handler(CommandHandler("find_brewery", find_brewery))
    app.add_handler(CommandHandler("cheap_beers", cheap_beers))
    app.add_handler(CommandHandler("serving_options", serving_options))
    app.add_handler(CommandHandler("brewery_map", brewery_map))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
