import os
import sys
import argparse
import shutil
import tempfile
import numpy as np
import soundfile as sf

# Import local pipeline modules
from audio import extract_audio, chunk_audio_vad
from transcription import AudioTranscriber
from analyzer import BoundaryAnalyzer
from llm import ContextualTagger

# Import rich elements for outstanding CLI aesthetics
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live

console = Console()

def generate_synthetic_demo_audio(filepath):
    """
    Generates a synthetic 90-second mono WAV file containing simulated speech
    and silent periods. This is used for demonstrating the tool if no input
    video is provided, ensuring zero-dependency runnable execution out-of-the-box.
    """
    sample_rate = 16000
    duration_sec = 90.0
    total_samples = int(duration_sec * sample_rate)
    data = np.zeros(total_samples, dtype=np.float32)
    
    # Heuristically fill sections with sine-wave mixtures to represent speech activity
    def fill_speech(start_sec, end_sec):
        start_idx = int(start_sec * sample_rate)
        end_idx = int(end_sec * sample_rate)
        t = np.arange(end_idx - start_idx) / sample_rate
        # Create a complex, modulated wave to simulate sound energy
        wave = (0.08 * np.sin(2 * np.pi * 180 * t) * np.sin(2 * np.pi * 3 * t) + 
                0.05 * np.cos(2 * np.pi * 320 * t) + 
                0.02 * np.sin(2 * np.pi * 640 * t))
        # Add slight random noise to simulate background environment
        noise = np.random.normal(0, 0.005, len(t))
        data[start_idx:end_idx] = wave + noise
        
    # We define speech blocks separated by natural gaps (silences)
    # Gap 1: 20.0s to 22.5s (2.5 seconds silence) -> Perfect for Ad Break 1
    fill_speech(0.0, 20.0)
    
    # Gap 2: 45.0s to 47.0s (2.0 seconds silence) -> Perfect for Ad Break 2
    fill_speech(22.5, 45.0)
    
    # Gap 3: 70.0s to 73.0s (3.0 seconds silence) -> Perfect for Ad Break 3
    fill_speech(47.0, 70.0)
    
    # End section
    fill_speech(73.0, 90.0)
    
    sf.write(filepath, data, sample_rate, subtype='PCM_16')
    console.print(f"[bold green][v][/bold green] Generated a 90-second synthetic audio demo file: [cyan]{filepath}[/cyan]")

def clean_up_dir(directory):
    """Safely removes a directory and its contents."""
    if os.path.exists(directory):
        try:
            shutil.rmtree(directory)
        except Exception as e:
            print(f"[Cleanup] Warning: Failed to delete directory {directory}: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Automated Video Ad-Marker & Contextual Prompt Generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "video_path", 
        nargs="?", 
        default=None,
        help="Path to the source video or audio file. If omitted, a synthetic audio file is generated for a demo run."
    )
    parser.add_argument(
        "--whisper-model", 
        default="tiny", 
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size to use for transcription."
    )
    parser.add_argument(
        "--device", 
        default="auto", 
        choices=["auto", "cpu", "cuda"],
        help="Device to run Whisper transcription on."
    )
    parser.add_argument(
        "--compute-type", 
        default="default",
        help="Whisper model quantization format (e.g. float16, int8, float32)."
    )
    parser.add_argument(
        "--llm-provider", 
        default="fallback", 
        choices=["fallback", "hf_api", "local", "gemini"],
        help="LLM provider for content tagging."
    )
    parser.add_argument(
        "--transcription-provider", 
        default="whisper", 
        choices=["whisper", "gemini"],
        help="Transcription provider to convert audio to text."
    )
    parser.add_argument(
        "--gemini-api-key", 
        default=None,
        help="Google AI Studio (Gemini) API Key (required for 'gemini' providers)."
    )
    parser.add_argument(
        "--hf-token", 
        default=None,
        help="Hugging Face User Access Token (required for 'hf_api' provider)."
    )
    parser.add_argument(
        "--local-llm-model", 
        default="Qwen/Qwen2.5-0.5B-Instruct",
        help="Model ID to download/load if using the 'local' LLM provider."
    )
    parser.add_argument(
        "--min-gap", 
        type=float, 
        default=1.5,
        help="Minimum silent gap duration (in seconds) to qualify as a conversational break."
    )
    parser.add_argument(
        "--min-chunk", 
        type=float, 
        default=20.0,
        help="Minimum audio chunk duration (in seconds) for VAD grouping."
    )
    parser.add_argument(
        "--max-chunk", 
        type=float, 
        default=30.0,
        help="Maximum audio chunk duration (in seconds) for VAD grouping before forcing a split."
    )
    parser.add_argument(
        "--energy-threshold", 
        type=float, 
        default=0.015,
        help="RMS energy threshold below which blocks are classified as silent/low activity."
    )
    parser.add_argument(
        "--json-output", 
        default=None,
        help="Path to save the final markers output as a JSON file."
    )
    parser.add_argument(
        "--mock-whisper", 
        action="store_true",
        help="Use mock transcriber instead of loading actual Whisper model (great for instant testing)."
    )
    parser.add_argument(
        "--keep-temp", 
        action="store_true",
        help="Do not delete extracted audio and temporary VAD audio chunks upon completion."
    )
    
    args = parser.parse_args()
    
    # ----------------------------------------------------
    # Header Banner Display
    # ----------------------------------------------------
    console.print()
    banner = Panel(
        Text("Automated Video Ad-Marker & Contextual Prompt Generator\n", style="bold cyan", justify="center") +
        Text("Memory-Safe VAD Chunking, Batched Transcription & Contextual Ad Recommendations", style="italic white", justify="center"),
        border_style="cyan",
        expand=False
    )
    console.print(banner)
    console.print()
    
    temp_dir = tempfile.mkdtemp(prefix="admarker_")
    vad_output_dir = os.path.join(temp_dir, "chunks")
    extracted_audio_path = os.path.join(temp_dir, "extracted_audio.wav")
    
    demo_mode = False
    target_path = args.video_path
    
    if target_path is None:
        console.print("[bold yellow][!] No input file specified. Entering DEMO mode...[/bold yellow]")
        demo_mode = True
        target_path = extracted_audio_path
        # Generate dummy wav file directly in extracted_audio_path
        generate_synthetic_demo_audio(target_path)
        # Enable mock whisper for demo run to make it zero-latency and offline-safe
        args.mock_whisper = True
    elif not os.path.exists(target_path):
        console.print(f"[bold red][ERROR] Specified input path does not exist: '{target_path}'[/bold red]")
        sys.exit(1)
        
    try:
        # ----------------------------------------------------
        # Execution Pipeline with Live Progress Spinner
        # ----------------------------------------------------
        steps = [
            ("Extracting audio stream...", "extract"),
            ("Analyzing VAD and chunking audio...", "vad"),
            ("Transcribing segments...", "transcribe"),
            ("Detecting conversational boundaries...", "analyze"),
            ("Generating LLM tags & recommendations...", "llm")
        ]
        
        chunks = []
        global_segments = []
        ad_breaks = []
        
        with Progress(
            SpinnerColumn(spinner_name="dots12", style="cyan"),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            # Step 1: Audio Extraction
            task_audio = progress.add_task(description="Extracting audio stream (ffmpeg/moviepy)...", total=1)
            if not demo_mode:
                extract_audio(target_path, extracted_audio_path)
            progress.update(task_audio, advance=1, description="[green][v] Audio stream extracted successfully")
            
            # Step 2: VAD Chunking
            task_vad = progress.add_task(description="Scanning voice activity & chunking (memory-safe)...", total=1)
            chunks = chunk_audio_vad(
                audio_path=extracted_audio_path,
                output_dir=vad_output_dir,
                min_chunk_len=args.min_chunk,
                max_chunk_len=args.max_chunk,
                energy_threshold=args.energy_threshold,
                silence_duration=0.5
            )
            progress.update(task_vad, advance=1, description=f"[green][v] VAD splitting complete ({len(chunks)} chunks)")
            
            # Step 3: Batched Transcription
            task_trans = progress.add_task(description="Stitching timeline & transcribing chunks...", total=1)
            transcriber = AudioTranscriber(
                model_size=args.whisper_model,
                device=args.device,
                compute_type=args.compute_type,
                use_mock=args.mock_whisper,
                provider=args.transcription_provider,
                api_key=args.gemini_api_key
            )
            global_segments = transcriber.transcribe_chunks(chunks)
            progress.update(task_trans, advance=1, description=f"[green][v] Transcribed {len(global_segments)} segments")
            
            # Step 4: Linguistic Boundary Finding
            task_boundary = progress.add_task(description="Searching linguistic breaks...", total=1)
            analyzer = BoundaryAnalyzer(min_gap_seconds=args.min_gap)
            ad_breaks = analyzer.find_ad_breaks(global_segments, top_n=3)
            progress.update(task_boundary, advance=1, description=f"[green][v] Identified top {len(ad_breaks)} ad breaks")
            
            # Step 5: Contextual Tagging
            task_tag = progress.add_task(description="Running contextual LLM classification...", total=len(ad_breaks))
            tagger = ContextualTagger(
                provider=args.llm_provider,
                hf_token=args.hf_token,
                local_model_id=args.local_llm_model,
                gemini_api_key=args.gemini_api_key
            )
            
            for ad_break in ad_breaks:
                progress.update(task_tag, description=f"Classifying Break {ad_break['break_id']}...")
                classification = tagger.tag_context(ad_break["preceding_context"])
                # Merge results
                ad_break.update(classification)
                progress.advance(task_tag)
                
            progress.update(task_tag, description="[green][v] Contextual tagging and classification complete")
            
        # ----------------------------------------------------
        # Output Presentation (Rich Tables)
        # ----------------------------------------------------
        console.print()
        console.print("[bold cyan]>>> METADATA ADS RECOMMENDATION TABLE[/bold cyan]")
        
        table = Table(show_header=True, header_style="bold magenta", border_style="cyan", show_lines=True)
        table.add_column("ID", style="bold green", justify="center")
        table.add_column("Timestamp", style="bold cyan", justify="center")
        table.add_column("Gap", style="yellow", justify="center")
        table.add_column("Preceding Conversational Context", style="white", max_width=30, overflow="fold")
        table.add_column("Category & Tone", style="bold magenta", max_width=18, overflow="fold")
        table.add_column("Targeted Ad Suggestions", style="green italic", max_width=25, overflow="fold")
        
        for brk in ad_breaks:
            ads_bullet = "\n".join([f"- {ad}" for ad in brk["ad_suggestions"]])
            cat_tone = f"[bold]{brk['category']}[/bold]\n[dim]Tone: {brk['tone']}[/dim]"
            
            table.add_row(
                f"AD-{brk['break_id']:02d}",
                brk["timestamp_str"],
                f"{brk['gap_duration']:.2f}s",
                brk["preceding_context"],
                cat_tone,
                ads_bullet
            )
            
        console.print(table)
        console.print()
        
        if args.json_output:
            import json
            with open(args.json_output, "w") as f:
                json.dump(ad_breaks, f, indent=2)
            console.print(f"[dim]Saved JSON output to {args.json_output}[/dim]")
        
        # Details about outputs saved or cleaned up
        if args.keep_temp:
            # Copy items out of temp dir to local project path
            saved_chunks_dir = "./vad_chunks"
            clean_up_dir(saved_chunks_dir)
            shutil.copytree(vad_output_dir, saved_chunks_dir)
            shutil.copy2(extracted_audio_path, "./extracted_audio.wav")
            console.print(f"[dim]Note: --keep-temp active. Extracted audio saved to './extracted_audio.wav' and VAD chunks in '{saved_chunks_dir}/'[/dim]")
        
    except KeyboardInterrupt:
        console.print("\n[bold red][INTERRUPTED] Process interrupted by user.[/bold red]")
    finally:
        # Cleanup
        if not args.keep_temp:
            clean_up_dir(temp_dir)
            
if __name__ == "__main__":
    main()
