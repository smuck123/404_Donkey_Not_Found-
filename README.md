# 404_Donkey_Not_Found-
# 404_Donkey_Not_Found-

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
