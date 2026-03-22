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
