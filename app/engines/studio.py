"""Studio Agent Engine for SwarmMojo by Buzburg AI.

High-fidelity multimodal production suite for video, cinema, photography, and visual design:
- Buzburg Directorial Optics: Grand Format 70mm, Modular 8K Cine, Super 35, Anamorphic, Vintage Prime, Tilt-Shift, Depth of Field
- Generation Gateways: local visual execution graphs, model bridges, and rendering pipelines
- Storyboarding & Scene Sequencing: multi-shot scene progression, camera motion vectors, lighting moods, pacing
- UI/UX & Visual Asset Craft: banner generation, design tokens, color harmonies, aspect-ratio safe zones
- Local Node Server Operator: execution bridge and graph templates
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# -------------------------------------------------------------------------
# Cinematic Camera, Lens, and Optics Presets
# -------------------------------------------------------------------------

CAMERA_PRESETS = {
    "grand_format_70mm": "grand format 70mm film camera, IMAX-grade organic grain, monumental depth of field",
    "modular_8k_digital": "modular 8K digital cinema camera, Arri Alexa 65 sensor look, clean dynamic range",
    "full_frame_cine": "full-frame digital cinema camera, 35mm filmic tone curve, natural highlight rolloff",
    "super_35_digital": "Super 35 studio digital camera, industry standard television/commercial aesthetic",
    "classic_16mm": "classic 16mm film camera, tactile grain, vintage halation, warm organic shadows",
    "large_format_digital": "premium large-format digital cinema camera, ultra-low distortion, photorealistic resolution",
}

LENS_PRESETS = {
    "classic_anamorphic": "classic 2x anamorphic lens, oval bokeh, horizontal blue lens flares, gentle edge falloff",
    "compact_anamorphic": "modern compact anamorphic lens, controlled cinematic flare, subtle breathing",
    "vintage_prime": "1970s vintage prime lens, un-coated elements, gentle halation diffusion, warm flare",
    "clinical_sharp_prime": "ultra-sharp modern cinema prime lens, chromatic aberration suppressed, edge-to-edge crispness",
    "creative_tilt_shift": "creative tilt-shift lens, selective focus plane, miniature perspective effect",
    "extreme_macro": "extreme 1:1 macro cinema lens, microscopic detail, hyper-shallow depth of field",
    "swirl_bokeh_portrait": "swirl bokeh portrait lens, Petzval aesthetic, dreamy radial background blur",
}

LIGHTING_PRESETS = {
    "golden_hour": "golden hour natural sunlight, warm 3200K side-lighting, elongated soft shadows",
    "cinematic_rembrandt": "dramatic Rembrandt studio lighting, 45-degree key light with triangle cheek highlight, deep contrast",
    "cyberpunk_neon": "high-contrast neon lighting, dual complementary rim lights (cyan and magenta), reflective wet surfaces",
    "volumetric_mist": "volumetric light rays breaking through haze, atmospheric diffusion, soft moody illumination",
    "soft_diffused_commercial": "large overhead softbox illumination, clean diffused shadows, premium commercial clarity",
    "moody_low_key": "low-key lighting, deep rich blacks, subtle edge rim accents, mysterious film-noir atmosphere",
}

ASPECT_RATIOS = {
    "16:9": {"width": 1920, "height": 1080, "label": "Landscape / YouTube / Television"},
    "9:16": {"width": 1080, "height": 1920, "label": "Vertical / Reels / TikTok / Shorts"},
    "1:1": {"width": 1080, "height": 1080, "label": "Square / Social Feed"},
    "2.39:1": {"width": 2560, "height": 1070, "label": "Cinemascope Widescreen"},
    "4:3": {"width": 1440, "height": 1080, "label": "Classic Television / Academy"},
    "21:9": {"width": 2560, "height": 1080, "label": "Ultrawide Monitor / Cinematic"},
    "4:5": {"width": 1080, "height": 1350, "label": "Portrait Social / Feed"},
}


# -------------------------------------------------------------------------
# Prompt Crafting & Compilation Engine
# -------------------------------------------------------------------------

class StudioPromptCompiler:
    """Compiles professional director-grade visual prompts from modular settings."""

    @classmethod
    def compile_cinematic_prompt(
        cls,
        subject: str,
        camera: str = "full_frame_cine",
        lens: str = "classic_anamorphic",
        focal_length_mm: int = 35,
        aperture: str = "f/1.8",
        lighting: str = "golden_hour",
        motion: Optional[str] = None,
        style_tags: Optional[List[str]] = None,
        negative_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Constructs an authoritative visual prompt ready for ComfyUI, Flux, Kling, or VEO."""
        cam_desc = CAMERA_PRESETS.get(camera, camera)
        lens_desc = LENS_PRESETS.get(lens, lens)
        light_desc = LIGHTING_PRESETS.get(lighting, lighting)

        focal_text = f"{focal_length_mm}mm focal length"
        aperture_text = f"{aperture} aperture, shallow depth of field" if "1." in aperture or "2." in aperture else f"{aperture} aperture, sharp focus"

        components = [
            subject.strip(),
            f"shot on {cam_desc}",
            f"equipped with {lens_desc}",
            f"{focal_text}, {aperture_text}",
            light_desc,
        ]

        if motion:
            components.append(f"camera motion: {motion}")

        if style_tags:
            components.extend(style_tags)

        # Baseline quality anchors
        components.append("8k resolution, photorealistic, color graded in DaVinci Resolve, 35mm film stock grain")

        compiled_prompt = ", ".join(components)
        compiled_negative = negative_prompt or (
            "cgi look, 3d cartoon render, plastic skin, oversaturated, deformed hands, "
            "flickering artifacts, blurry, watermark, low quality, oversmoothed"
        )

        return {
            "prompt": compiled_prompt,
            "negative_prompt": compiled_negative,
            "camera_rig": {
                "camera": camera,
                "lens": lens,
                "focal_length": focal_length_mm,
                "aperture": aperture,
                "lighting": lighting,
                "motion": motion,
            },
        }


# -------------------------------------------------------------------------
# Scene Storyboard & Multi-Shot Director
# -------------------------------------------------------------------------

@dataclass
class StoryboardShot:
    shot_number: int
    duration_seconds: float
    description: str
    camera: str
    lens: str
    lighting: str
    camera_movement: str
    audio_description: str
    prompt: str = ""
    negative_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StoryboardDirector:
    """Manages scene breakdown, shot pacing, and continuity across sequences."""

    def __init__(self, title: str = "Untitled Sequence"):
        self.title = title
        self.shots: List[StoryboardShot] = []

    def add_shot(
        self,
        duration_seconds: float,
        description: str,
        camera: str = "full_frame_cine",
        lens: str = "classic_anamorphic",
        lighting: str = "cinematic_rembrandt",
        camera_movement: str = "slow smooth tracking shot",
        audio_description: str = "ambient room tone with subtle score",
    ) -> StoryboardShot:
        shot_num = len(self.shots) + 1
        compiled = StudioPromptCompiler.compile_cinematic_prompt(
            subject=description,
            camera=camera,
            lens=lens,
            lighting=lighting,
            motion=camera_movement,
        )
        shot = StoryboardShot(
            shot_number=shot_num,
            duration_seconds=duration_seconds,
            description=description,
            camera=camera,
            lens=lens,
            lighting=lighting,
            camera_movement=camera_movement,
            audio_description=audio_description,
            prompt=compiled["prompt"],
            negative_prompt=compiled["negative_prompt"],
        )
        self.shots.append(shot)
        return shot

    def compile_storyboard(self) -> Dict[str, Any]:
        total_time = sum(s.duration_seconds for s in self.shots)
        return {
            "title": self.title,
            "total_shots": len(self.shots),
            "total_duration_seconds": round(total_time, 2),
            "shots": [s.to_dict() for s in self.shots],
        }


# -------------------------------------------------------------------------
# ComfyUI Execution Graph Generator & Local Bridge
# -------------------------------------------------------------------------

class ComfyUIBridge:
    """Generates execution graphs and handles IPC with local ComfyUI API servers."""

    def __init__(self, host: str = "http://127.0.0.1:8188"):
        self.host = host.rstrip("/")

    @classmethod
    def build_flux_t2i_workflow(
        cls,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 25,
        guidance: float = 3.5,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Constructs a production-ready ComfyUI API execution graph for Flux / SDXL."""
        actual_seed = seed if seed is not None else int(time.time() * 1000) % 1_000_000_000
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "flux1-dev.safetensors"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["1", 1], "text": prompt},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["1", 1], "text": negative_prompt},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": actual_seed,
                    "steps": steps,
                    "cfg": guidance,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "SwarmMojo_Studio", "images": ["6", 0]},
            },
        }

    @classmethod
    def build_i2v_motion_workflow(
        cls,
        image_path: str,
        motion_bucket_id: int = 127,
        fps: int = 24,
        frames: int = 49,
    ) -> Dict[str, Any]:
        """Constructs a video generation graph (e.g. SVD / Wan / Kling node style)."""
        return {
            "10": {
                "class_type": "LoadImage",
                "inputs": {"image": image_path},
            },
            "11": {
                "class_type": "SVD_img2vid_Conditioning",
                "inputs": {
                    "init_image": ["10", 0],
                    "width": 1024,
                    "height": 576,
                    "video_frames": frames,
                    "motion_bucket_id": motion_bucket_id,
                    "fps": fps,
                    "augmentation_level": 0.0,
                },
            },
            "12": {
                "class_type": "SaveAnimatedWEBP",
                "inputs": {"filename_prefix": "SwarmMojo_Video", "fps": fps},
            },
        }

    def check_status(self) -> Dict[str, Any]:
        """Checks if local ComfyUI server is reachable."""
        try:
            req = urllib.request.Request(f"{self.host}/system_stats", headers={"User-Agent": "SwarmMojo"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"online": True, "host": self.host, "stats": data}
        except Exception as e:
            return {"online": False, "host": self.host, "error": str(e)}


# -------------------------------------------------------------------------
# Studio Agent Engine Master Orchestrator
# -------------------------------------------------------------------------

class StudioAgentEngine:
    """Master Studio Agent for end-to-end visual and video direction."""

    def __init__(self, workspace_root: str = "."):
        self.root = Path(workspace_root).resolve()
        self.studio_dir = self.root / ".mojo_studio"
        self.studio_dir.mkdir(parents=True, exist_ok=True)
        self.comfy = ComfyUIBridge()

    def generate_shot_prompt(
        self,
        subject: str,
        camera: str = "full_frame_cine",
        lens: str = "classic_anamorphic",
        focal_length_mm: int = 35,
        aperture: str = "f/1.8",
        lighting: str = "golden_hour",
        motion: Optional[str] = "cinematic slow push-in",
    ) -> Dict[str, Any]:
        """Generates a professional cinematic prompt with optics specification."""
        return StudioPromptCompiler.compile_cinematic_prompt(
            subject=subject,
            camera=camera,
            lens=lens,
            focal_length_mm=focal_length_mm,
            aperture=aperture,
            lighting=lighting,
            motion=motion,
        )

    def create_storyboard(self, title: str, shots_spec: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Constructs an integrated storyboard across multiple scenes."""
        director = StoryboardDirector(title=title)
        for s in shots_spec:
            director.add_shot(
                duration_seconds=float(s.get("duration", 4.0)),
                description=s.get("description", "Scene action"),
                camera=s.get("camera", "full_frame_cine"),
                lens=s.get("lens", "classic_anamorphic"),
                lighting=s.get("lighting", "cinematic_rembrandt"),
                camera_movement=s.get("camera_movement", "slow tracking shot"),
                audio_description=s.get("audio", "subtle cinematic score"),
            )
        board = director.compile_storyboard()
        save_file = self.studio_dir / f"storyboard_{int(time.time())}.json"
        save_file.write_text(json.dumps(board, indent=2), encoding="utf-8")
        board["saved_to"] = str(save_file)
        return board

    def export_comfyui_workflow(
        self,
        prompt: str,
        negative_prompt: str = "",
        aspect_ratio: str = "16:9",
        steps: int = 25,
    ) -> Dict[str, Any]:
        """Exports a ComfyUI execution graph mapped to standard aspect ratio."""
        ratio_info = ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS["16:9"])
        w, h = ratio_info["width"], ratio_info["height"]
        # Scale to max 1024 on longest edge for optimal base model efficiency
        if w >= h:
            eff_w = 1024
            eff_h = int((1024 * h / w) // 16 * 16)
        else:
            eff_h = 1024
            eff_w = int((1024 * w / h) // 16 * 16)

        workflow = ComfyUIBridge.build_flux_t2i_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=eff_w,
            height=eff_h,
            steps=steps,
        )
        out_file = self.studio_dir / "comfyui_workflow.json"
        out_file.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        return {
            "status": "ready",
            "dimensions": f"{eff_w}x{eff_h}",
            "aspect_ratio": aspect_ratio,
            "workflow_file": str(out_file),
            "workflow": workflow,
        }

    def craft_banner_spec(
        self,
        platform: str,
        headline: str,
        subtext: str,
        style: str = "bold_typography_glassmorphism",
        primary_color: str = "#4F46E5",
        accent_color: str = "#06B6D4",
    ) -> Dict[str, Any]:
        """Generates pixel-perfect UI/UX banner layouts based on platform standards."""
        platform_dims = {
            "youtube_banner": (2560, 1440, "safe zone 1546x423 centered"),
            "twitter_header": (1500, 500, "safe zone 1500x500 with avatar bottom-left buffer"),
            "linkedin_banner": (1584, 396, "safe zone 1350x396 with profile avatar bottom-left"),
            "website_hero": (1920, 1080, "responsive 16:9 hero section"),
            "instagram_portrait": (1080, 1350, "4:5 feed view"),
        }
        w, h, safe_zone = platform_dims.get(platform.lower(), (1200, 630, "centered content zone"))
        return {
            "platform": platform,
            "dimensions": {"width": w, "height": h},
            "safe_zone": safe_zone,
            "style": style,
            "typography": {
                "headline": headline,
                "subtext": subtext,
                "font_family": "Inter, system-ui, sans-serif",
                "weight": "bold",
            },
            "palette": {
                "primary": primary_color,
                "accent": accent_color,
                "background": "#0F172A",
                "text": "#F8FAFC",
            },
        }
