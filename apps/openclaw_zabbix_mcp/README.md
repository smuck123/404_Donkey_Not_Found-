# OpenClaw Zabbix MCP Bridge

Endpoints:
- /health
- /tools
- /get_zabbix_problems?limit=20
- /get_host_status?host_name=linux01
- /get_host_interfaces?host_name=linux01
- /get_recent_events?host_name=linux01&limit=20
- /get_trigger_details?trigger_id=12345
- /get_item_last_value?host_name=linux01&item_key=system.cpu.load[all,avg1]
- /search_hosts?search_text=web&limit=20
- /list_host_groups?limit=100
- /summarize_hosts?limit=100

## Warsaw Beer Festival Telegram assistant

The Telegram bot now includes a Warsaw Beer Festival assistant that imports and normalizes:
- Beer list data from `https://warsawbeerfestival.com/beer-list/`
- Event schedule data from `https://warsawbeerfestival.com/`
- Exhibitor/floor map hints from `https://warszawskifestiwalpiwa.pl/mapa_interaktywna.pdf`

Data is stored in SQLite at `apps/openclaw_zabbix_mcp/warsaw_beer_festival.db`.

### Install
```bash
cd apps/openclaw_zabbix_mcp
pip install -r requirements.txt
```

### Telegram commands
- `/next_beer`
- `/recommend <query>`
- `/drank <beer name>`
- `/rate <beer name> <1-5>`
- `/history`
- `/set_max_abv <value>`
- `/set_location <zone>`
- `/next_event`
- `/events_today`
- `/beer_and_event`
- `/random_beer`
- `/find_beer <name>`
- `/find_brewery <name>`
