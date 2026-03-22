# 404_Donkey_Not_Found-

A collection of local AI tools and web apps for:

- chatting with Ollama models,
- editing and administering a chat/web UI,
- generating images,
- searching local retrieval data, and
- integrating Zabbix workflows.

## Repository layout

- `apps/chat_admin_webgui/` – chat UI plus admin tools for editing content, managing projects, repos, chats, and generated assets.
- `apps/ollama_webgui/` – FastAPI + frontend app for chatting with Ollama and generating Zabbix widget scaffolding.
- `apps/openclaw_zabbix_mcp/` – Zabbix bridge service with monitoring-oriented endpoints.
- `apps/404donkey_rag/` – indexing and search scripts used for retrieval.
- `scripts/` – standalone helper scripts, including SDXL image generation and Ollama image analysis.
- `deploy/systemd/` – systemd service definitions and overrides.

## Image tooling

Create a real SDXL image:

```bash
python scripts/make_image_sdxl.py \
  "glamorous adult woman, detailed face, realistic skin, cinematic lighting, fashion photography" \
  --model stabilityai/stable-diffusion-xl-base-1.0 \
  --width 832 \
  --height 1216 \
  --steps 30 \
  --guidance 6.5
```

Analyze an image with an Ollama vision model:

```bash
python scripts/look_image_ollama.py path/to/image.png \
  --model llava:latest \
  --prompt "Describe this image and extract any visible text."
```

## Notes

- This repository contains multiple independent apps rather than a single entry point.
- Review app-specific files under `apps/` for service configuration and runtime requirements.
