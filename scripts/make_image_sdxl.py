#!/usr/bin/env python3
"""Generate an image with an SDXL-compatible diffusers pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an image with Stable Diffusion XL.")
    parser.add_argument("prompt", help="Text prompt for image generation.")
    parser.add_argument("--model", default="stabilityai/stable-diffusion-xl-base-1.0", help="Hugging Face model id or local model path.")
    parser.add_argument("--negative-prompt", default="", help="Optional negative prompt.")
    parser.add_argument("--width", type=int, default=832, help="Image width, divisible by 8.")
    parser.add_argument("--height", type=int, default=1216, help="Image height, divisible by 8.")
    parser.add_argument("--steps", type=int, default=30, help="Inference steps.")
    parser.add_argument("--guidance", type=float, default=6.5, help="Classifier-free guidance scale.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic seed.")
    parser.add_argument("--output", default=None, help="Output image path. Defaults to outputs/images/<timestamp>.png")
    parser.add_argument("--device", default="cuda", help="Torch device, e.g. cuda or cpu.")
    parser.add_argument("--dtype", choices=["float16", "bfloat16", "float32"], default="float16", help="Torch dtype to use.")
    return parser


def validate_dimensions(width: int, height: int) -> None:
    for name, value in {"width": width, "height": height}.items():
        if value < 256 or value % 8 != 0:
            raise SystemExit(f"{name} must be at least 256 and divisible by 8, got {value}")


def main() -> None:
    args = build_parser().parse_args()
    validate_dimensions(args.width, args.height)

    import torch
    from diffusers import StableDiffusionXLPipeline

    dtype = getattr(torch, args.dtype)
    pipe = StableDiffusionXLPipeline.from_pretrained(args.model, torch_dtype=dtype, use_safetensors=True)
    pipe = pipe.to(args.device)

    generator = None
    if args.seed is not None:
        generator = torch.Generator(device=args.device).manual_seed(args.seed)

    result = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative_prompt or None,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        generator=generator,
    )

    output_path = Path(args.output) if args.output else Path("outputs/images") / f"sdxl_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.images[0].save(output_path)
    print(output_path)


if __name__ == "__main__":
    main()
