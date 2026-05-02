import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
import os
import subprocess
import random
import json
import base64
from m_gpux.core.metrics import FUNCTIONS as _METRICS_FUNCTIONS
from m_gpux.core import _select_profile, _activate_profile, AVAILABLE_GPUS, AVAILABLE_CPUS
from m_gpux.core.ui import arrow_select

app = typer.Typer(
    help="Generate videos from text prompts using LTX-2.3 on Modal GPUs.",
    short_help="AI Video Generation",
    no_args_is_help=True,
)
console = Console()

# ─── Pipeline presets ─────────────────────────────────────────

PIPELINES = {
    "1": ("distilled",          "Distilled — Fastest (8 steps, ~2 min)",       "ltx-2.3-22b-distilled-1.1.safetensors", False),
    "2": ("ti2vid_two_stages",  "Two-Stage — Best quality (40 steps, ~10 min)", "ltx-2.3-22b-dev.safetensors",          True),
}

RESOLUTION_PRESETS = {
    "1": (768,  512,  "Landscape 768x512"),
    "2": (512,  768,  "Portrait 512x768"),
    "3": (512,  512,  "Square 512x512"),
    "4": (1024, 576,  "Widescreen 1024x576"),
    "5": (576,  1024, "Tall 576x1024"),
}

# Frame counts must satisfy 8k+1 format
FRAME_PRESETS = {
    "1": (25,  "1 second (25 frames)"),
    "2": (49,  "2 seconds (49 frames)"),
    "3": (97,  "~4 seconds (97 frames)"),
    "4": (121, "~5 seconds (121 frames)"),
}

# ─── Modal script template ───────────────────────────────────

VIDEO_TEMPLATE = '''import modal
import subprocess
import os
import sys
import time
import base64

# __METRICS__

app = modal.App("m-gpux-video-gen")

video_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .apt_install("git", "ffmpeg", "libsndfile1", "libsndfile1-dev")
    .pip_install("huggingface_hub", "hf-transfer")
    .run_commands(
        "pip install uv",
        "git clone https://github.com/Lightricks/LTX-2.git /opt/LTX-2",
        "cd /opt/LTX-2 && uv sync",
    )
    .env(ENV_DICT_PLACEHOLDER)
)

LTX_PYTHON = "/opt/LTX-2/.venv/bin/python"

model_cache = modal.Volume.from_name("m-gpux-ltx-cache", create_if_missing=True)
output_vol = modal.Volume.from_name("m-gpux-video-output", create_if_missing=True)

PROMPT_B64 = "PROMPT_B64_PLACEHOLDER"


@app.function(
    image=video_image,
    COMPUTE_SPEC_PLACEHOLDER,
    timeout=86400,
    volumes={"/models": model_cache, "/output": output_vol},
)
def generate():
    from huggingface_hub import hf_hub_download, snapshot_download

    _print_metrics()

    prompt = base64.b64decode(PROMPT_B64).decode()

    # ── Model paths ──
    ckpt_file = "CKPT_FILE_PLACEHOLDER"
    ckpt_path = "/models/" + ckpt_file
    upscaler_path = "/models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
    gemma_root = "/models/gemma-3-12b-it-qat-q4_0-unquantized"

    # ── Download models if not cached ──
    if not os.path.exists(ckpt_path):
        print("[M-GPUX] Downloading " + ckpt_file + " ... (one-time, may take several minutes)")
        hf_hub_download("Lightricks/LTX-2.3", ckpt_file, local_dir="/models")
        model_cache.commit()
    else:
        print("[M-GPUX] Checkpoint cached: " + ckpt_file)

    if not os.path.exists(upscaler_path):
        print("[M-GPUX] Downloading spatial upscaler...")
        hf_hub_download("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors", local_dir="/models")
        model_cache.commit()
    else:
        print("[M-GPUX] Upscaler cached.")

    if not os.path.exists(os.path.join(gemma_root, "config.json")):
        print("[M-GPUX] Downloading Gemma 3 text encoder... (one-time, may take several minutes)")
        hf_token = os.environ.get("HF_TOKEN", None)
        snapshot_download("google/gemma-3-12b-it-qat-q4_0-unquantized", local_dir=gemma_root, token=hf_token)
        model_cache.commit()
    else:
        print("[M-GPUX] Gemma encoder cached.")

    EXTRA_DOWNLOAD_PLACEHOLDER

    print("[M-GPUX] All models ready.")

    # ── Build inference command ──
    height = HEIGHT_PLACEHOLDER
    width = WIDTH_PLACEHOLDER
    num_frames = NUM_FRAMES_PLACEHOLDER
    frame_rate = FRAME_RATE_PLACEHOLDER
    seed = SEED_PLACEHOLDER

    timestamp = str(int(time.time()))
    output_file = "video_" + str(seed) + "_" + timestamp + ".mp4"
    output_path = "/output/" + output_file

    cmd = [
        LTX_PYTHON, "-m", "ltx_pipelines.PIPELINE_MODULE_PLACEHOLDER",
        "--checkpoint-path", ckpt_path,
        "--spatial-upsampler-path", upscaler_path,
        "--gemma-root", gemma_root,
        "--prompt", prompt,
        "--output-path", output_path,
        "--height", str(height),
        "--width", str(width),
        "--num-frames", str(num_frames),
        "--frame-rate", str(frame_rate),
        "--seed", str(seed),
    ]

    EXTRA_CMD_PLACEHOLDER
    QUANTIZATION_PLACEHOLDER

    print("[M-GPUX] === Video Generation ===")
    print("[M-GPUX] Prompt: " + prompt[:200])
    print("[M-GPUX] Resolution: " + str(width) + "x" + str(height))
    print("[M-GPUX] Frames: " + str(num_frames) + " @ " + str(frame_rate) + "fps")
    print("[M-GPUX] Pipeline: PIPELINE_MODULE_PLACEHOLDER")
    print("[M-GPUX] Running inference...")
    print("")

    proc = subprocess.run(cmd)

    if proc.returncode != 0:
        print("[M-GPUX] ERROR: Generation failed (exit code " + str(proc.returncode) + ")")
        return

    output_vol.commit()
    print("")
    print("[M-GPUX] ========================================")
    print("[M-GPUX]   VIDEO GENERATED SUCCESSFULLY!")
    print("[M-GPUX] ========================================")
    print("[M-GPUX] File: " + output_file)
    print("[M-GPUX]")
    print("[M-GPUX] Download with:")
    print("  modal volume get m-gpux-video-output " + output_file + " .")
    print("")
    print("[M-GPUX] List all videos:")
    print("  modal volume ls m-gpux-video-output")


@app.local_entrypoint()
def main():
    generate.remote()
'''

# ─── Generate command ─────────────────────────────────────────


@app.command("generate")
def generate():
    """Generate a video from a text prompt using LTX-2.3."""

    console.print(Panel.fit(
        "[bold magenta]M-GPUX Video Generator[/bold magenta]\n"
        "Generate videos from text prompts using LTX-2.3 (22B) on Modal GPUs.\n"
        "Model: [cyan]Lightricks/LTX-2.3[/cyan] — DiT-based audio-video foundation model",
        border_style="cyan",
    ))

    # ── Step 0: Workspace / Profile ──
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    # ── Step 1: Pipeline ──
    console.print("\n[bold cyan]Step 1: Select Pipeline[/bold cyan]")
    pipeline_options = []
    for k in PIPELINES:
        module, desc, _, _ = PIPELINES[k]
        pipeline_options.append((module, desc))
    pipeline_idx = arrow_select(pipeline_options, title="Pipeline", default=0)
    key = list(PIPELINES.keys())[pipeline_idx]
    pipeline_module, _, ckpt_file, needs_lora = PIPELINES[key]
    console.print(f"  [green]Pipeline:[/green] [bold]{pipeline_options[pipeline_idx][1]}[/bold]")

    # ── Step 2: Compute ──
    console.print(f"\n[bold cyan]Step 2: Choose Compute[/bold cyan]  [dim](recommended: H100 or A100-80GB for 22B model)[/dim]")
    compute_type_options = [
        ("GPU", "GPU acceleration (recommended for video generation)"),
        ("CPU", "CPU-only (very slow for video, use only for testing)"),
    ]
    compute_type_idx = arrow_select(compute_type_options, title="Compute Type", default=0)
    if compute_type_idx == 1:
        cpu_keys = list(AVAILABLE_CPUS.keys())
        cpu_options = []
        for k in cpu_keys:
            cores, mem, desc = AVAILABLE_CPUS[k]
            cpu_options.append((f"{cores} cores", desc))
        cpu_idx = arrow_select(cpu_options, title="Select CPU", default=3)
        selected_cores, selected_memory, _ = AVAILABLE_CPUS[cpu_keys[cpu_idx]]
        compute_spec = f'cpu={selected_cores}, memory={selected_memory}'
        compute_label = f"CPU ({selected_cores} cores)"
    else:
        gpu_keys = list(AVAILABLE_GPUS.keys())
        gpu_options = []
        default_gpu_idx = 8  # fallback
        for i, k in enumerate(gpu_keys):
            gpu, desc = AVAILABLE_GPUS[k]
            rec = " <- recommended" if gpu in ("H100", "A100-80GB") else ""
            gpu_options.append((gpu, f"{desc}{rec}"))
            if gpu == "H100":
                default_gpu_idx = i
        gpu_idx = arrow_select(gpu_options, title="Select GPU", default=default_gpu_idx)
        selected_gpu = AVAILABLE_GPUS[gpu_keys[gpu_idx]][0]
        compute_spec = f'gpu="{selected_gpu}"'
        compute_label = selected_gpu
    console.print(f"  [green]Compute:[/green] [bold]{compute_label}[/bold]")

    # ── Step 3: Prompt ──
    console.print("\n[bold cyan]Step 3: Enter Prompt[/bold cyan]")
    console.print("  [dim]Describe the scene in detail: actions, camera angles, lighting, colors.[/dim]")
    console.print("  [dim]Start with the main action. Keep within 200 words for best results.[/dim]")
    prompt = Prompt.ask("  Prompt")
    if not prompt.strip():
        console.print("[red]Prompt cannot be empty.[/red]")
        raise typer.Exit(1)
    console.print(f"  [green]Prompt:[/green] {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

    # ── Step 4: Resolution ──
    console.print("\n[bold cyan]Step 4: Resolution[/bold cyan]  [dim](must be divisible by 32)[/dim]")
    res_options = []
    for k in RESOLUTION_PRESETS:
        w, h, desc = RESOLUTION_PRESETS[k]
        res_options.append((f"{w}x{h}", desc))
    res_idx = arrow_select(res_options, title="Resolution", default=0)
    res_key = list(RESOLUTION_PRESETS.keys())[res_idx]
    width, height, _ = RESOLUTION_PRESETS[res_key]
    console.print(f"  [green]Resolution:[/green] [bold]{width}x{height}[/bold]")

    # ── Step 5: Duration ──
    console.print("\n[bold cyan]Step 5: Duration[/bold cyan]  [dim](frame count must be 8k+1)[/dim]")
    frame_options = []
    for k in FRAME_PRESETS:
        frames, desc = FRAME_PRESETS[k]
        frame_options.append((str(frames), desc))
    frame_idx = arrow_select(frame_options, title="Duration", default=2)
    frame_key = list(FRAME_PRESETS.keys())[frame_idx]
    num_frames = FRAME_PRESETS[frame_key][0]
    frame_rate = 25
    duration = num_frames / frame_rate
    console.print(f"  [green]Frames:[/green] [bold]{num_frames}[/bold] ({duration:.1f}s at {frame_rate}fps)")

    # ── Step 6: HuggingFace Token ──
    console.print("\n[bold cyan]Step 6: HuggingFace Token[/bold cyan]")
    console.print("  [dim]Required for downloading Gemma text encoder (gated model).[/dim]")
    console.print("  [dim]Get your token at: https://huggingface.co/settings/tokens[/dim]")
    console.print("  [dim]Also accept Gemma license at: https://huggingface.co/google/gemma-3-12b-it-qat-q4_0-unquantized[/dim]")

    # Try to read from env or previous input
    default_token = os.environ.get("HF_TOKEN", "")
    hf_token = Prompt.ask("  HF Token", default=default_token, password=True)
    if not hf_token.strip():
        console.print("[yellow]  Warning: No HF token provided. Gemma download may fail.[/yellow]")
    else:
        console.print("  [green]HF Token:[/green] ****" + hf_token[-4:])

    # ── Step 7: Advanced options ──
    console.print("\n[bold cyan]Step 7: Advanced Options[/bold cyan]  [dim](press Enter for defaults)[/dim]")

    seed_str = Prompt.ask("  Seed (random if empty)", default="")
    seed = int(seed_str) if seed_str.strip().isdigit() else random.randint(0, 2**32 - 1)
    console.print(f"  [green]Seed:[/green] {seed}")

    use_fp8 = Prompt.ask(
        "  Use FP8 quantization? (saves ~50% VRAM, recommended)",
        choices=["y", "n"], default="y",
    ) == "y"
    if use_fp8:
        console.print("  [green]FP8:[/green] Enabled")

    # ── Build script ──
    prompt_b64 = base64.b64encode(prompt.encode()).decode()
    hf_token_b64 = base64.b64encode(hf_token.encode()).decode() if hf_token.strip() else ""
    env_dict_parts = [
        '"HF_HUB_ENABLE_HF_TRANSFER": "1"',
        '"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"',
    ]
    if hf_token.strip():
        env_dict_parts.append('"HF_TOKEN": "HF_TOKEN_PLACEHOLDER"')
    env_dict = "{" + ", ".join(env_dict_parts) + "}"

    # Extra downloads & CLI args for two-stage pipeline
    extra_download = ""
    extra_cmd = ""
    if needs_lora:
        lora_file = "ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
        extra_download = (
            f'lora_path = "/models/{lora_file}"\n'
            f'    if not os.path.exists(lora_path):\n'
            f'        print("[M-GPUX] Downloading distilled LoRA...")\n'
            f'        hf_hub_download("Lightricks/LTX-2.3", "{lora_file}", local_dir="/models")\n'
            f'        model_cache.commit()\n'
            f'    else:\n'
            f'        print("[M-GPUX] Distilled LoRA cached.")'
        )
        extra_cmd = f'cmd.extend(["--distilled-lora", "/models/{lora_file}", "0.8"])'

    quantization_code = ""
    if use_fp8:
        quantization_code = 'cmd.extend(["--quantization", "fp8-cast"])'

    script = (VIDEO_TEMPLATE
        .replace("PROMPT_B64_PLACEHOLDER", prompt_b64)
        .replace("COMPUTE_SPEC_PLACEHOLDER", compute_spec)
        .replace("CKPT_FILE_PLACEHOLDER", ckpt_file)
        .replace("PIPELINE_MODULE_PLACEHOLDER", pipeline_module)
        .replace("HEIGHT_PLACEHOLDER", str(height))
        .replace("WIDTH_PLACEHOLDER", str(width))
        .replace("NUM_FRAMES_PLACEHOLDER", str(num_frames))
        .replace("FRAME_RATE_PLACEHOLDER", str(frame_rate))
        .replace("SEED_PLACEHOLDER", str(seed))
        .replace("ENV_DICT_PLACEHOLDER", env_dict)
        .replace("HF_TOKEN_PLACEHOLDER", hf_token.strip() if hf_token.strip() else "")
        .replace("EXTRA_DOWNLOAD_PLACEHOLDER", extra_download)
        .replace("EXTRA_CMD_PLACEHOLDER", extra_cmd)
        .replace("QUANTIZATION_PLACEHOLDER", quantization_code)
        .replace("# __METRICS__", _METRICS_FUNCTIONS)
    )

    runner_file = "modal_runner.py"
    with open(runner_file, "w", encoding="utf-8") as f:
        f.write(script)

    console.print(f"\n[cyan]Generated script: {runner_file}[/cyan]")
    console.print(Syntax(script, "python", theme="monokai", line_numbers=True))

    # ── Summary panel ──
    console.print(Panel(
        f"[bold]Video Generation Config[/bold]\n\n"
        f"  [green]Pipeline:[/green]    {pipeline_module}\n"
        f"  [green]GPU:[/green]         {selected_gpu}\n"
        f"  [green]Model:[/green]       {ckpt_file}\n"
        f"  [green]Resolution:[/green]  {width}x{height}\n"
        f"  [green]Frames:[/green]      {num_frames} ({duration:.1f}s at {frame_rate}fps)\n"
        f"  [green]FP8:[/green]         {'Yes' if use_fp8 else 'No'}\n"
        f"  [green]Seed:[/green]        {seed}\n"
        f"  [green]Prompt:[/green]      {prompt[:80]}{'...' if len(prompt) > 80 else ''}\n\n"
        f"[dim]First run downloads models (~50GB total). Subsequent runs use cached weights.\n"
        f"Image build takes 5-10 min on first run (LTX-2 + dependencies).[/dim]",
        title="READY TO GENERATE",
        border_style="magenta",
    ))

    console.print(Panel(
        f"[bold green]Script `{runner_file}` has been created.[/bold green]\n\n"
        f"You can open this file to:\n"
        f"  - Change the GPU type or timeout\n"
        f"  - Adjust resolution, frame count, or frame rate\n"
        f"  - Modify the prompt or pipeline parameters\n\n"
        f"Your code is 100% transparent and editable.",
        title="WAITING FOR CONFIGURATION", expand=False, border_style="cyan",
    ))

    choice = Prompt.ask(
        "\n[bold cyan]Press [Enter] to run, or type 'cancel' to abort[/bold cyan]",
        default="",
    )
    if choice.strip().lower() == "cancel":
        console.print("[yellow]Cancelled.[/yellow]")
        return

    console.print(f"\n[bold green]Starting video generation on {compute_label}...[/bold green]")
    console.print("[dim]First run: image build (~10 min) + model download (~50GB) + inference.[/dim]")
    console.print("[dim]Subsequent runs: cached image + cached models = much faster.[/dim]\n")

    try:
        subprocess.run(["modal", "run", runner_file])
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return

    console.print(Panel(
        f"[bold green]Generation complete![/bold green]\n\n"
        f"[bold]Download your video:[/bold]\n"
        f"  [bold yellow]modal volume get m-gpux-video-output <filename> .[/bold yellow]\n\n"
        f"[bold]List all generated videos:[/bold]\n"
        f"  [bold yellow]modal volume ls m-gpux-video-output[/bold yellow]\n\n"
        f"[bold]Or use the shortcut:[/bold]\n"
        f"  [bold yellow]m-gpux video download[/bold yellow]\n\n"
        f"[dim]Videos are stored in Modal volume 'm-gpux-video-output'.[/dim]",
        title="NEXT STEPS",
        border_style="green",
    ))

    del_choice = Prompt.ask(
        f"\n[bold cyan]Delete {runner_file}?[/bold cyan]",
        choices=["y", "n"],
        default="n",
    )
    if del_choice == "y":
        try:
            os.remove(runner_file)
            console.print("[dim]Cleaned up.[/dim]")
        except OSError:
            pass


# ─── Download command ─────────────────────────────────────────


@app.command("download")
def download(filename: str = typer.Argument(None, help="Video filename to download")):
    """Download generated videos from Modal volume."""
    if filename:
        console.print(f"[cyan]Downloading {filename}...[/cyan]")
        subprocess.run(["modal", "volume", "get", "m-gpux-video-output", filename, "."])
    else:
        console.print("[cyan]Videos in m-gpux-video-output:[/cyan]\n")
        subprocess.run(["modal", "volume", "ls", "m-gpux-video-output"])
        console.print(f"\n[dim]Download a video: m-gpux video download <filename>[/dim]")


# ─── Storyboard Modal template ───────────────────────────────

STORYBOARD_TEMPLATE = '''import modal
import subprocess
import os
import sys
import time
import json
import base64

# __METRICS__

app = modal.App("m-gpux-video-storyboard")

video_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .apt_install("git", "ffmpeg", "libsndfile1", "libsndfile1-dev")
    .pip_install("huggingface_hub", "hf-transfer")
    .run_commands(
        "pip install uv",
        "git clone https://github.com/Lightricks/LTX-2.git /opt/LTX-2",
        "cd /opt/LTX-2 && uv sync",
    )
    .env(ENV_DICT_PLACEHOLDER)
)

LTX_PYTHON = "/opt/LTX-2/.venv/bin/python"

model_cache = modal.Volume.from_name("m-gpux-ltx-cache", create_if_missing=True)
output_vol = modal.Volume.from_name("m-gpux-video-output", create_if_missing=True)

SCENES_B64 = "SCENES_B64_PLACEHOLDER"
ANCHOR_PROMPT_B64 = "ANCHOR_PROMPT_B64_PLACEHOLDER"
ANCHOR_STRENGTH = ANCHOR_STRENGTH_PLACEHOLDER


def _download_models():
    """Download all models if not cached. Called once before parallel generation."""
    from huggingface_hub import hf_hub_download, snapshot_download

    ckpt_file = "CKPT_FILE_PLACEHOLDER"
    ckpt_path = "/models/" + ckpt_file
    upscaler_path = "/models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
    gemma_root = "/models/gemma-3-12b-it-qat-q4_0-unquantized"

    if not os.path.exists(ckpt_path):
        print("[M-GPUX] Downloading " + ckpt_file + " ...")
        hf_hub_download("Lightricks/LTX-2.3", ckpt_file, local_dir="/models")
        model_cache.commit()
    else:
        print("[M-GPUX] Checkpoint cached: " + ckpt_file)

    if not os.path.exists(upscaler_path):
        print("[M-GPUX] Downloading spatial upscaler...")
        hf_hub_download("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors", local_dir="/models")
        model_cache.commit()

    if not os.path.exists(os.path.join(gemma_root, "config.json")):
        print("[M-GPUX] Downloading Gemma 3 text encoder...")
        hf_token = os.environ.get("HF_TOKEN", None)
        snapshot_download("google/gemma-3-12b-it-qat-q4_0-unquantized", local_dir=gemma_root, token=hf_token)
        model_cache.commit()

    EXTRA_DOWNLOAD_PLACEHOLDER

    print("[M-GPUX] All models ready.")


@app.function(
    image=video_image,
    COMPUTE_SPEC_PLACEHOLDER,
    timeout=86400,
    volumes={"/models": model_cache, "/output": output_vol},
)
def generate_scene(scene_data: str) -> str:
    """Generate a single scene clip. Returns the output filename or empty string on failure."""
    _print_metrics()
    model_cache.reload()

    data = json.loads(scene_data)
    scene_num = data["scene_num"]
    total = data["total"]
    prompt = data["prompt"]
    scene_seed = data["seed"]
    height = data["height"]
    width = data["width"]
    num_frames = data["num_frames"]
    frame_rate = data["frame_rate"]
    pipeline_module = data["pipeline"]

    ckpt_file = "CKPT_FILE_PLACEHOLDER"
    ckpt_path = "/models/" + ckpt_file
    upscaler_path = "/models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
    gemma_root = "/models/gemma-3-12b-it-qat-q4_0-unquantized"

    clip_name = "scene_" + str(scene_num).zfill(3) + ".mp4"
    clip_path = "/output/" + clip_name

    print("")
    print("[M-GPUX] ════════════════════════════════════════")
    print("[M-GPUX]  SCENE " + str(scene_num) + "/" + str(total))
    print("[M-GPUX] ════════════════════════════════════════")
    print("[M-GPUX] Prompt: " + prompt[:200])
    print("[M-GPUX] Seed: " + str(scene_seed))
    print("")

    anchor_frame = data.get("anchor_frame", "")
    anchor_strength = data.get("anchor_strength", 0.0)

    cmd = [
        LTX_PYTHON, "-m", "ltx_pipelines." + pipeline_module,
        "--checkpoint-path", ckpt_path,
        "--spatial-upsampler-path", upscaler_path,
        "--gemma-root", gemma_root,
        "--prompt", prompt,
        "--output-path", clip_path,
        "--height", str(height),
        "--width", str(width),
        "--num-frames", str(num_frames),
        "--frame-rate", str(frame_rate),
        "--seed", str(scene_seed),
    ]

    # Image conditioning for character consistency
    if anchor_frame and os.path.exists(anchor_frame) and anchor_strength > 0:
        cmd.extend(["--image", anchor_frame, "0", str(anchor_strength)])
        print("[M-GPUX] Using anchor frame (strength=" + str(anchor_strength) + ")")

    EXTRA_CMD_PLACEHOLDER
    QUANTIZATION_PLACEHOLDER

    proc = subprocess.run(cmd)

    if proc.returncode != 0:
        print("[M-GPUX] WARNING: Scene " + str(scene_num) + " failed!")
        return ""

    output_vol.commit()
    print("[M-GPUX] Scene " + str(scene_num) + " done: " + clip_name)
    return clip_name


@app.function(
    image=video_image,
    COMPUTE_SPEC_PLACEHOLDER,
    timeout=86400,
    volumes={"/models": model_cache, "/output": output_vol},
)
def download_models_task():
    """Pre-download all models before parallel generation."""
    _download_models()
    return "ok"


@app.function(
    image=video_image,
    COMPUTE_SPEC_PLACEHOLDER,
    timeout=86400,
    volumes={"/models": model_cache, "/output": output_vol},
)
def generate_anchor(anchor_data: str) -> str:
    """Generate anchor scene and extract a reference frame for character consistency."""
    _print_metrics()
    model_cache.reload()

    data = json.loads(anchor_data)
    prompt = data["prompt"]
    seed = data["seed"]
    height = data["height"]
    width = data["width"]
    num_frames = data["num_frames"]
    frame_rate = data["frame_rate"]
    pipeline_module = data["pipeline"]

    ckpt_file = "CKPT_FILE_PLACEHOLDER"
    ckpt_path = "/models/" + ckpt_file
    upscaler_path = "/models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
    gemma_root = "/models/gemma-3-12b-it-qat-q4_0-unquantized"

    anchor_clip = "/output/anchor_ref.mp4"
    anchor_frame = "/output/anchor_frame.jpg"

    print("[M-GPUX] ═══════════════════════════════════════")
    print("[M-GPUX]  GENERATING ANCHOR (character reference)")
    print("[M-GPUX] ═══════════════════════════════════════")
    print("[M-GPUX] Prompt: " + prompt[:200])
    print("")

    cmd = [
        LTX_PYTHON, "-m", "ltx_pipelines." + pipeline_module,
        "--checkpoint-path", ckpt_path,
        "--spatial-upsampler-path", upscaler_path,
        "--gemma-root", gemma_root,
        "--prompt", prompt,
        "--output-path", anchor_clip,
        "--height", str(height),
        "--width", str(width),
        "--num-frames", str(num_frames),
        "--frame-rate", str(frame_rate),
        "--seed", str(seed),
    ]

    EXTRA_CMD_PLACEHOLDER
    QUANTIZATION_PLACEHOLDER

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print("[M-GPUX] WARNING: Anchor generation failed! Continuing without reference.")
        return ""

    # Extract middle frame as reference image
    mid_sec = str(round(num_frames / frame_rate / 2, 2))
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", anchor_clip,
        "-ss", mid_sec, "-frames:v", "1",
        "-q:v", "2", anchor_frame,
    ]
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("[M-GPUX] WARNING: Frame extraction failed!")
        return ""

    output_vol.commit()
    print("[M-GPUX] Anchor frame saved: anchor_frame.jpg")
    return anchor_frame


@app.function(
    image=video_image,
    timeout=86400,
    volumes={"/output": output_vol},
)
def concat_clips(clip_names_json: str) -> str:
    """Concatenate scene clips into a final video using ffmpeg."""
    data = json.loads(clip_names_json)
    clip_names = data["clips"]
    base_seed = data["base_seed"]

    output_vol.reload()

    os.makedirs("/tmp/concat", exist_ok=True)

    # Filter out empty (failed) clips and sort by scene number
    valid_clips = sorted([c for c in clip_names if c])
    if not valid_clips:
        print("[M-GPUX] ERROR: No clips to concatenate!")
        return ""

    print("[M-GPUX] Concatenating " + str(len(valid_clips)) + " clips...")

    concat_list = "/tmp/concat/list.txt"
    with open(concat_list, "w") as f:
        for clip in valid_clips:
            f.write("file '/output/" + clip + "'\\n")

    timestamp = str(int(time.time()))
    final_file = "storyboard_" + str(base_seed) + "_" + timestamp + ".mp4"
    final_path = "/output/" + final_file

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        final_path,
    ]
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        print("[M-GPUX] Stream copy failed, re-encoding...")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            final_path,
        ]
        proc = subprocess.run(ffmpeg_cmd)
        if proc.returncode != 0:
            print("[M-GPUX] ERROR: Concatenation failed!")
            return ""

    output_vol.commit()
    print("[M-GPUX] Final video: " + final_file)
    return final_file


@app.local_entrypoint()
def main():
    scenes = json.loads(base64.b64decode(SCENES_B64).decode())

    height = HEIGHT_PLACEHOLDER
    width = WIDTH_PLACEHOLDER
    num_frames = NUM_FRAMES_PLACEHOLDER
    frame_rate = FRAME_RATE_PLACEHOLDER
    base_seed = SEED_PLACEHOLDER
    pipeline_module = "PIPELINE_MODULE_PLACEHOLDER"
    total = len(scenes)

    print("[M-GPUX] ════════════════════════════════════════════════")
    print("[M-GPUX]   STORYBOARD: " + str(total) + " scenes")
    print("[M-GPUX]   Running in PARALLEL on Modal")
    print("[M-GPUX] ════════════════════════════════════════════════")
    print("")

    # Step 1: Pre-download models (one container)
    print("[M-GPUX] Step 1: Downloading models (if needed)...")
    download_models_task.remote()
    print("[M-GPUX] Models ready.")
    print("")

    # Step 2: Anchor frame for character consistency (optional)
    anchor_prompt_b64 = ANCHOR_PROMPT_B64
    anchor_strength = ANCHOR_STRENGTH
    anchor_frame = ""

    if anchor_prompt_b64 and anchor_strength > 0:
        anchor_prompt = base64.b64decode(anchor_prompt_b64).decode()
        print("[M-GPUX] Step 2: Generating anchor frame for character consistency...")
        print("[M-GPUX] Anchor prompt: " + anchor_prompt[:150])
        anchor_data = json.dumps({
            "prompt": anchor_prompt,
            "seed": base_seed,
            "height": height,
            "width": width,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
            "pipeline": pipeline_module,
        })
        anchor_frame = generate_anchor.remote(anchor_data)
        if anchor_frame:
            print("[M-GPUX] Anchor frame ready: " + anchor_frame)
        else:
            print("[M-GPUX] Anchor failed, continuing without character reference.")
        print("")
    else:
        print("[M-GPUX] Step 2: No anchor (character sync OFF)")
        print("")

    # Step 3: Generate all scenes in parallel
    print("[M-GPUX] Step 3: Generating " + str(total) + " scenes in parallel...")
    scene_inputs = []
    for i, scene in enumerate(scenes):
        scene_inputs.append(json.dumps({
            "scene_num": i + 1,
            "total": total,
            "prompt": scene["prompt"],
            "seed": base_seed + i,
            "height": height,
            "width": width,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
            "pipeline": pipeline_module,
            "anchor_frame": anchor_frame,
            "anchor_strength": anchor_strength,
        }))

    clip_names = list(generate_scene.map(scene_inputs))
    successful = [c for c in clip_names if c]
    print("")
    print("[M-GPUX] Generated " + str(len(successful)) + "/" + str(total) + " scenes successfully.")

    if not successful:
        print("[M-GPUX] ERROR: No scenes generated!")
        return

    # Step 4: Concatenate clips
    print("")
    print("[M-GPUX] Step 4: Concatenating clips...")
    concat_data = json.dumps({"clips": clip_names, "base_seed": base_seed})
    final_file = concat_clips.remote(concat_data)

    if final_file:
        total_duration = len(successful) * num_frames / frame_rate
        print("")
        print("[M-GPUX] ════════════════════════════════════════════════")
        print("[M-GPUX]   STORYBOARD COMPLETE!")
        print("[M-GPUX] ════════════════════════════════════════════════")
        print("[M-GPUX] Scenes: " + str(len(successful)) + "/" + str(total))
        print("[M-GPUX] Duration: ~" + str(round(total_duration, 1)) + "s")
        print("[M-GPUX] File: " + final_file)
        print("[M-GPUX]")
        print("[M-GPUX] Download:")
        print("  modal volume get m-gpux-video-output " + final_file + " .")
    else:
        print("[M-GPUX] ERROR: Concatenation failed. Download individual clips:")
        print("  modal volume ls m-gpux-video-output")
'''


# ─── Storyboard command ──────────────────────────────────────

SCENE_DURATION_PRESETS = {
    "1": (25,  "1 second per scene"),
    "2": (49,  "2 seconds per scene"),
    "3": (97,  "~4 seconds per scene"),
    "4": (121, "~5 seconds per scene (best quality)"),
}


@app.command("storyboard")
def storyboard():
    """Generate a long video from a multi-scene storyboard script."""

    console.print(Panel.fit(
        "[bold magenta]M-GPUX Storyboard Video Generator[/bold magenta]\n"
        "Create long-form videos by chaining multiple scenes.\n"
        "Each scene is generated as a ~5s clip, then all clips are concatenated.\n"
        "Model: [cyan]Lightricks/LTX-2.3[/cyan]",
        border_style="cyan",
    ))

    # ── Step 0: Workspace ──
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    # ── Step 1: Pipeline ──
    console.print("\n[bold cyan]Step 1: Select Pipeline[/bold cyan]")
    pipeline_options = []
    for k in PIPELINES:
        module, desc, _, _ = PIPELINES[k]
        pipeline_options.append((module, desc))
    pipeline_idx = arrow_select(pipeline_options, title="Pipeline", default=0)
    key = list(PIPELINES.keys())[pipeline_idx]
    pipeline_module, _, ckpt_file, needs_lora = PIPELINES[key]
    console.print(f"  [green]Pipeline:[/green] [bold]{pipeline_options[pipeline_idx][1]}[/bold]")

    # ── Step 2: Compute ──
    console.print(f"\n[bold cyan]Step 2: Choose Compute[/bold cyan]  [dim](recommended: H100 for storyboard)[/dim]")
    compute_type_options = [
        ("GPU", "GPU acceleration (recommended for video generation)"),
        ("CPU", "CPU-only (very slow for video, use only for testing)"),
    ]
    compute_type_idx = arrow_select(compute_type_options, title="Compute Type", default=0)
    if compute_type_idx == 1:
        cpu_keys = list(AVAILABLE_CPUS.keys())
        cpu_options = []
        for k in cpu_keys:
            cores, mem, desc = AVAILABLE_CPUS[k]
            cpu_options.append((f"{cores} cores", desc))
        cpu_idx = arrow_select(cpu_options, title="Select CPU", default=3)
        selected_cores, selected_memory, _ = AVAILABLE_CPUS[cpu_keys[cpu_idx]]
        compute_spec = f'cpu={selected_cores}, memory={selected_memory}'
        compute_label = f"CPU ({selected_cores} cores)"
    else:
        gpu_keys = list(AVAILABLE_GPUS.keys())
        gpu_options = []
        default_gpu_idx = 8
        for i, k in enumerate(gpu_keys):
            gpu, desc = AVAILABLE_GPUS[k]
            rec = " <- recommended" if gpu == "H100" else ""
            gpu_options.append((gpu, f"{desc}{rec}"))
            if gpu == "H100":
                default_gpu_idx = i
        gpu_idx = arrow_select(gpu_options, title="Select GPU", default=default_gpu_idx)
        selected_gpu = AVAILABLE_GPUS[gpu_keys[gpu_idx]][0]
        compute_spec = f'gpu="{selected_gpu}"'
        compute_label = selected_gpu
    console.print(f"  [green]Compute:[/green] [bold]{compute_label}[/bold]")

    # ── Step 3: Resolution ──
    console.print("\n[bold cyan]Step 3: Resolution[/bold cyan]")
    res_options = []
    for k in RESOLUTION_PRESETS:
        w, h, desc = RESOLUTION_PRESETS[k]
        res_options.append((f"{w}x{h}", desc))
    res_idx = arrow_select(res_options, title="Resolution", default=0)
    res_key = list(RESOLUTION_PRESETS.keys())[res_idx]
    width, height, _ = RESOLUTION_PRESETS[res_key]
    console.print(f"  [green]Resolution:[/green] [bold]{width}x{height}[/bold]")

    # ── Step 4: Duration per scene ──
    console.print("\n[bold cyan]Step 4: Duration per Scene[/bold cyan]")
    dur_options = []
    for k in SCENE_DURATION_PRESETS:
        frames, desc = SCENE_DURATION_PRESETS[k]
        dur_options.append((str(frames), desc))
    dur_idx = arrow_select(dur_options, title="Scene Duration", default=3)
    dur_key = list(SCENE_DURATION_PRESETS.keys())[dur_idx]
    num_frames = SCENE_DURATION_PRESETS[dur_key][0]
    frame_rate = 25
    scene_duration = num_frames / frame_rate
    console.print(f"  [green]Per scene:[/green] [bold]{num_frames} frames[/bold] ({scene_duration:.1f}s)")

    # ── Step 5: Storyboard / Scenes ──
    console.print("\n[bold cyan]Step 5: Write Your Storyboard[/bold cyan]")

    # Show planning guide
    examples = [
        (30,  "30s"),
        (60,  "1 min"),
        (120, "2 min"),
        (180, "3 min"),
        (300, "5 min"),
    ]
    guide_table = Table(title="Scene Planning Guide", show_edge=False, padding=(0, 2))
    guide_table.add_column("Target", style="cyan")
    guide_table.add_column(f"Scenes needed ({scene_duration:.0f}s each)", style="bold yellow")
    guide_table.add_column(f"Est. time (distilled)", style="dim")
    for target_sec, label in examples:
        n = int(target_sec / scene_duration) + (1 if target_sec % scene_duration else 0)
        est_min = n * 2
        guide_table.add_row(label, str(n), f"~{est_min} min GPU")
    console.print(guide_table)
    console.print("")

    # Choose input mode
    console.print("  [bold]How do you want to enter scenes?[/bold]")
    input_mode_options = [
        ("one-by-one", "Enter scenes one at a time (interactive)"),
        ("bulk-paste", "Paste all scenes at once (separated by ---)"),
    ]
    input_mode_idx = arrow_select(input_mode_options, title="Input Mode", default=1)

    scenes = []

    if input_mode_idx == 1:
        # ── Bulk paste mode ──
        console.print("")
        console.print(Panel(
            "[bold]Paste your storyboard below.[/bold]\n\n"
            "[bold yellow]Format for LLM-generated scripts:[/bold yellow]\n\n"
            "  CHARACTERS:\n"
            "  Wife: young woman, long black hair, pink pajamas, round face\n"
            "  Husband: tall man, short hair, blue pajamas, glasses\n"
            "  ---\n"
            "  Wide shot of bedroom at night, moonlight through window.\n"
            "  Wife reaches for blanket. Husband clutches it tighter.\n"
            "  ---\n"
            "  Close-up of Wife pulling blanket, slow motion, warm lighting.\n"
            "  ---\n"
            "  Husband rolls over dramatically, camera zooms in on his face.\n\n"
            "[dim]Rules:[/dim]\n"
            "  - First block: [bold]CHARACTERS:[/bold] defines appearances (auto-injected into every scene)\n"
            "  - Separate scenes with [bold yellow]---[/bold yellow] on its own line\n"
            "  - Reference character names in scenes (auto-replaced with full description)\n"
            "  - End with an empty line (press Enter)\n\n"
            "[bold cyan]LLM Prompt template you can copy:[/bold cyan]\n"
            '[dim]  "Write a storyboard for a {duration} video about {topic}.\n'
            "   Use this exact format:\n"
            "   CHARACTERS:\n"
            "   Name: detailed visual appearance description\n"
            "   ---\n"
            "   Scene prompt with Name doing action, camera angle, lighting.\n"
            "   ---\n"
            "   Next scene...\n"
            "   \n"
            "   Rules:\n"
            "   - Each scene = ~5 seconds of video\n"
            "   - Need {N} scenes for {duration}\n"
            "   - Describe visuals only: actions, camera, lighting, environment\n"
            "   - Use character Name (will be replaced with appearance)\n"
            '   - No markdown, no numbering, just plain text"[/dim]',
            border_style="cyan",
            title="STORYBOARD FORMAT",
        ))

        console.print("\n  [cyan]Paste your storyboard (end with empty line):[/cyan]\n")
        lines = []
        while True:
            try:
                line = input("  ")
            except EOFError:
                break
            if line.strip() == "":
                break
            lines.append(line)

        # Parse: first block may be CHARACTERS, rest are scenes
        characters = {}
        current_block_lines = []

        # Split into blocks by ---
        blocks = []
        for line in lines:
            if line.strip() == "---":
                if current_block_lines:
                    blocks.append(current_block_lines)
                current_block_lines = []
            else:
                current_block_lines.append(line)
        if current_block_lines:
            blocks.append(current_block_lines)

        # Check if first block is CHARACTERS
        if blocks:
            first_line = blocks[0][0].strip()
            if first_line.upper().startswith("CHARACTERS"):
                char_block = blocks.pop(0)
                for cl in char_block:
                    cl = cl.strip()
                    if cl.upper().startswith("CHARACTERS"):
                        # "CHARACTERS:" alone or "CHARACTERS: Name: desc"
                        after = cl.split(":", 1)[1].strip() if ":" in cl else ""
                        if after and ":" in after:
                            name, desc = after.split(":", 1)
                            if name.strip() and desc.strip():
                                characters[name.strip()] = desc.strip()
                    elif ":" in cl:
                        name, desc = cl.split(":", 1)
                        if name.strip() and desc.strip():
                            characters[name.strip()] = desc.strip()

        scene_lines_all = blocks

        # Show parsed characters
        if characters:
            console.print(f"\n  [bold green]Characters ({len(characters)}):[/bold green]")
            for name, desc in characters.items():
                console.print(f"    [cyan]{name}[/cyan]: {desc[:80]}")

        # Build scenes with character injection
        for block in scene_lines_all:
            prompt = " ".join(l.strip() for l in block).strip()
            if not prompt:
                continue
            # Replace character names with full descriptions
            for name, desc in characters.items():
                prompt = prompt.replace(name, f"{name} ({desc})")
            scenes.append({"prompt": prompt})

        if not scenes:
            console.print("[red]No scenes found! Make sure to separate scenes with ---[/red]")
            raise typer.Exit(1)

        console.print(f"\n  [green]Parsed {len(scenes)} scenes.[/green]")

    else:
        # ── One-by-one mode ──
        console.print(f"\n  [dim]Each scene becomes a ~{scene_duration:.0f}s clip.[/dim]")
        console.print("  [dim]Type 'done' when finished. Type 'del N' to remove scene N.[/dim]")
        console.print("")

        while True:
            scene_num = len(scenes) + 1
            prompt = Prompt.ask(f"  [cyan]Scene {scene_num}[/cyan]", default="done")

            if prompt.strip().lower() == "done":
                if len(scenes) < 1:
                    console.print("  [red]Need at least 1 scene![/red]")
                    continue
                break

            if prompt.strip().lower().startswith("del "):
                try:
                    del_idx = int(prompt.strip().split()[1]) - 1
                    if 0 <= del_idx < len(scenes):
                        removed = scenes.pop(del_idx)
                        console.print(f"  [yellow]Removed scene {del_idx + 1}: {removed['prompt'][:50]}...[/yellow]")
                    else:
                        console.print(f"  [red]Invalid scene number.[/red]")
                except (ValueError, IndexError):
                    console.print(f"  [red]Usage: del N[/red]")
                continue

            if not prompt.strip():
                continue

            scenes.append({"prompt": prompt.strip()})
            console.print(f"  [green]  Added.[/green] ({len(scenes)} scenes, ~{len(scenes) * scene_duration:.0f}s total)")

    # Show storyboard summary
    total_duration = len(scenes) * scene_duration
    console.print("")
    table = Table(title=f"Storyboard — {len(scenes)} scenes, ~{total_duration:.0f}s total")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("Prompt", style="white")
    table.add_column("Duration", style="dim", width=8)
    for i, s in enumerate(scenes):
        table.add_row(str(i + 1), s["prompt"][:100] + ("..." if len(s["prompt"]) > 100 else ""), f"{scene_duration:.1f}s")
    console.print(table)

    # ── Step 6: HuggingFace Token ──
    console.print("\n[bold cyan]Step 6: HuggingFace Token[/bold cyan]")
    default_token = os.environ.get("HF_TOKEN", "")
    hf_token = Prompt.ask("  HF Token", default=default_token, password=True)
    if not hf_token.strip():
        console.print("[yellow]  Warning: No HF token. Gemma download may fail.[/yellow]")
    else:
        console.print("  [green]HF Token:[/green] ****" + hf_token[-4:])

    # ── Step 7: Advanced ──
    console.print("\n[bold cyan]Step 7: Advanced Options[/bold cyan]")
    seed_str = Prompt.ask("  Base seed (random if empty)", default="")
    base_seed = int(seed_str) if seed_str.strip().isdigit() else random.randint(0, 2**32 - 1)
    console.print(f"  [green]Base seed:[/green] {base_seed} (scene N uses seed {base_seed}+N)")

    use_fp8 = Prompt.ask(
        "  Use FP8 quantization?",
        choices=["y", "n"], default="y",
    ) == "y"

    # ── Step 8: Character Sync ──
    console.print("\n[bold cyan]Step 8: Character Consistency[/bold cyan]")
    console.print(Panel(
        "[bold]Anchor Frame Method[/bold]\n\n"
        "Generates a 'character reference' scene FIRST, extracts a key frame,\n"
        "then uses it as [bold]image conditioning[/bold] for ALL other scenes.\n"
        "This helps maintain consistent character appearance across scenes.\n\n"
        "[dim]How it works:[/dim]\n"
        "  1. You provide a special prompt showing all characters together\n"
        "  2. LTX-2 generates a short reference clip\n"
        "  3. A frame is extracted and passed to every scene via --image\n"
        "  4. The model uses this as visual reference (strength controls influence)\n\n"
        "[bold yellow]Strength guide:[/bold yellow]\n"
        "  [cyan]0.3[/cyan] = Light guidance (characters similar, scenes very flexible)\n"
        "  [cyan]0.5[/cyan] = Balanced (recommended)\n"
        "  [cyan]0.7[/cyan] = Strong guidance (very consistent, but less scene variety)\n"
        "  [cyan]0.0[/cyan] = OFF (no anchor, each scene fully independent)",
        border_style="yellow",
        title="CHARACTER SYNC",
    ))

    use_anchor = Prompt.ask(
        "  Enable character sync?",
        choices=["y", "n"], default="y" if len(scenes) > 3 else "n",
    ) == "y"

    anchor_prompt = ""
    anchor_strength = 0.0

    if use_anchor:
        console.print("\n  [bold]Write an anchor prompt[/bold] showing all characters together.")
        console.print('  [dim]Example: "Medium shot of a young Vietnamese woman with long black hair[/dim]')
        console.print('  [dim]wearing pink pajamas and a tall Vietnamese man with short hair wearing[/dim]')
        console.print('  [dim]blue pajamas, standing together in a cozy bedroom, warm lighting,[/dim]')
        console.print('  [dim]cinematic portrait, detailed faces"[/dim]')
        console.print("")

        anchor_prompt = Prompt.ask("  Anchor prompt")
        if not anchor_prompt.strip():
            console.print("  [yellow]No anchor prompt. Character sync disabled.[/yellow]")
            use_anchor = False
        else:
            strength_str = Prompt.ask("  Anchor strength", default="0.5")
            try:
                anchor_strength = float(strength_str)
                anchor_strength = max(0.0, min(1.0, anchor_strength))
            except ValueError:
                anchor_strength = 0.5
            console.print(f"  [green]Anchor:[/green] ON (strength={anchor_strength})")
            console.print(f"  [dim]Anchor prompt: {anchor_prompt[:80]}...[/dim]")

    # ── Build script ──
    scenes_b64 = base64.b64encode(json.dumps(scenes).encode()).decode()
    anchor_prompt_b64 = base64.b64encode(anchor_prompt.encode()).decode() if anchor_prompt.strip() else ""
    env_dict_parts = [
        '"HF_HUB_ENABLE_HF_TRANSFER": "1"',
        '"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"',
    ]
    if hf_token.strip():
        env_dict_parts.append('"HF_TOKEN": "HF_TOKEN_PLACEHOLDER"')
    env_dict = "{" + ", ".join(env_dict_parts) + "}"

    extra_download = ""
    extra_cmd = ""
    if needs_lora:
        lora_file = "ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
        extra_download = (
            f'lora_path = "/models/{lora_file}"\n'
            f'    if not os.path.exists(lora_path):\n'
            f'        print("[M-GPUX] Downloading distilled LoRA...")\n'
            f'        hf_hub_download("Lightricks/LTX-2.3", "{lora_file}", local_dir="/models")\n'
            f'        model_cache.commit()\n'
            f'    else:\n'
            f'        print("[M-GPUX] Distilled LoRA cached.")'
        )
        extra_cmd = f'cmd.extend(["--distilled-lora", "/models/{lora_file}", "0.8"])'

    quantization_code = ""
    if use_fp8:
        quantization_code = 'cmd.extend(["--quantization", "fp8-cast"])'

    script = (STORYBOARD_TEMPLATE
        .replace("SCENES_B64_PLACEHOLDER", scenes_b64)
        .replace("ANCHOR_PROMPT_B64_PLACEHOLDER", anchor_prompt_b64)
        .replace("ANCHOR_STRENGTH_PLACEHOLDER", str(anchor_strength))
        .replace("COMPUTE_SPEC_PLACEHOLDER", compute_spec)
        .replace("CKPT_FILE_PLACEHOLDER", ckpt_file)
        .replace("PIPELINE_MODULE_PLACEHOLDER", pipeline_module)
        .replace("HEIGHT_PLACEHOLDER", str(height))
        .replace("WIDTH_PLACEHOLDER", str(width))
        .replace("NUM_FRAMES_PLACEHOLDER", str(num_frames))
        .replace("FRAME_RATE_PLACEHOLDER", str(frame_rate))
        .replace("SEED_PLACEHOLDER", str(base_seed))
        .replace("ENV_DICT_PLACEHOLDER", env_dict)
        .replace("HF_TOKEN_PLACEHOLDER", hf_token.strip() if hf_token.strip() else "")
        .replace("EXTRA_DOWNLOAD_PLACEHOLDER", extra_download)
        .replace("EXTRA_CMD_PLACEHOLDER", extra_cmd)
        .replace("QUANTIZATION_PLACEHOLDER", quantization_code)
        .replace("# __METRICS__", _METRICS_FUNCTIONS)
    )

    runner_file = "modal_runner.py"
    with open(runner_file, "w", encoding="utf-8") as f:
        f.write(script)

    console.print(f"\n[cyan]Generated script: {runner_file}[/cyan]")

    # ── Summary ──
    est_time_per_scene = "~2 min" if not needs_lora else "~10 min"
    est_parallel = "~2-5 min" if not needs_lora else "~10-15 min"
    anchor_label = f"[bold green]ON[/bold green] (strength={anchor_strength})" if use_anchor else "[dim]OFF[/dim]"
    console.print(Panel(
        f"[bold]Storyboard Config[/bold]\n\n"
        f"  [green]Scenes:[/green]      {len(scenes)}\n"
        f"  [green]Total:[/green]       ~{total_duration:.0f}s ({total_duration / 60:.1f} min)\n"
        f"  [green]Per scene:[/green]   {scene_duration:.1f}s @ {frame_rate}fps\n"
        f"  [green]Compute:[/green]     {compute_label}\n"
        f"  [green]Pipeline:[/green]    {pipeline_module}\n"
        f"  [green]FP8:[/green]         {'Yes' if use_fp8 else 'No'}\n"
        f"  [green]Mode:[/green]        [bold yellow]PARALLEL[/bold yellow] ({len(scenes)} containers)\n"
        f"  [green]Char Sync:[/green]   {anchor_label}\n"
        f"  [green]Est. time:[/green]   {est_time_per_scene}/scene, {est_parallel} total (parallel)\n\n"
        f"[dim]Scenes run in PARALLEL on Modal, then concatenated with ffmpeg.[/dim]",
        title="READY TO GENERATE STORYBOARD",
        border_style="magenta",
    ))

    choice = Prompt.ask(
        "\n[bold cyan]Press [Enter] to run, or type 'cancel' to abort[/bold cyan]",
        default="",
    )
    if choice.strip().lower() == "cancel":
        console.print("[yellow]Cancelled.[/yellow]")
        return

    console.print(f"\n[bold green]Starting PARALLEL storyboard generation ({len(scenes)} scenes) on {compute_label}...[/bold green]")
    console.print(f"[dim]Each scene runs on its own Modal container. All generate simultaneously.[/dim]\n")

    try:
        subprocess.run(["modal", "run", runner_file])
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return

    console.print(Panel(
        f"[bold green]Storyboard complete![/bold green]\n\n"
        f"[bold]Download your video:[/bold]\n"
        f"  [bold yellow]modal volume get m-gpux-video-output <filename> .[/bold yellow]\n\n"
        f"[bold]List all videos:[/bold]\n"
        f"  [bold yellow]m-gpux video download[/bold yellow]\n",
        title="STORYBOARD DONE",
        border_style="green",
    ))

    del_choice = Prompt.ask(
        f"\n[bold cyan]Delete {runner_file}?[/bold cyan]",
        choices=["y", "n"],
        default="n",
    )
    if del_choice == "y":
        try:
            os.remove(runner_file)
            console.print("[dim]Cleaned up.[/dim]")
        except OSError:
            pass


# ─── Plugin registration ──────────────────────────────────────
from m_gpux.core.plugin import PluginBase as _PluginBase


class VideoPlugin(_PluginBase):
    name = "video"
    help = "Generate videos from text prompts using LTX-2.3."
    rich_help_panel = "Compute Engine"

    def register(self, root_app):
        root_app.add_typer(
            app,
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )
