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
    next_event,
    events_today,
    beer_and_event,
    random_beer,
    find_beer,
    find_brewery,
)



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
    await _reply(update, bot_capabilities_text())


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
        if text in ["what can you do", "help", "/help", "commands", "bot help"]:
            await _reply(update, bot_capabilities_text())
            return

        if text in ["my chat id", "chat id", "what is my chat id"]:
            await _reply(update, f"Your chat id is: {update.effective_chat.id}")
            return

        if text in ["list registered chats", "show registered chats"]:
            chats = list_chats()
            if not chats:
                await _reply(update, "No registered chats yet.")
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

        reply = chat_with_ai(
            f"The user wrote: {text_raw}\n"
            "Reply as a short helpful assistant. "
            "Never explain JSON structure unless the user explicitly asks for parsing or programming help. "
            "If it sounds like monitoring or firewall traffic analysis, keep it operational and concise. "
            "If it is casual chat, answer normally."
        )
        await _reply(update, reply)

    except Exception as e:
        await _reply(update, f"Error: {e}")


def main():
    validate_config()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next_beer", next_beer))
    app.add_handler(CommandHandler("recommend", recommend))
    app.add_handler(CommandHandler("drank", drank))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("set_max_abv", set_max_abv))
    app.add_handler(CommandHandler("set_location", set_location))
    app.add_handler(CommandHandler("next_event", next_event))
    app.add_handler(CommandHandler("events_today", events_today))
    app.add_handler(CommandHandler("beer_and_event", beer_and_event))
    app.add_handler(CommandHandler("random_beer", random_beer))
    app.add_handler(CommandHandler("find_beer", find_beer))
    app.add_handler(CommandHandler("find_brewery", find_brewery))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()

