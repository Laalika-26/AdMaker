import os
import subprocess
import tempfile
import numpy as np
import soundfile as sf

def extract_audio(video_path, output_audio_path):
    """
    Extracts audio from a video file and saves it as a 16kHz mono WAV file.
    Uses moviepy with a robust fallback to ffmpeg subprocess if moviepy is unavailable/fails.
    """
    print(f"[Audio] Extracting audio from '{video_path}' to '{output_audio_path}'...")
    
    # Try moviepy first
    try:
        # moviepy imports can vary depending on version
        try:
            # pyrefly: ignore [missing-import]
            from moviepy.editor import AudioFileClip
        except ImportError:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            
        clip = AudioFileClip(video_path)
        # Force 16000Hz, 1 channel (mono), 16-bit PCM WAV
        clip.write_audiofile(
            output_audio_path,
            fps=16000,
            nbytes=2,
            codec='pcm_s16le',
            ffmpeg_params=["-ac", "1"],
            logger=None # Suppress moviepy progress bar to avoid cluttering CLI
        )
        clip.close()
        print("[Audio] Audio extraction via moviepy completed successfully.")
        return True
    except Exception as e:
        print(f"[Audio] Moviepy extraction failed or unavailable ({e}). Falling back to FFmpeg subprocess...")
        return extract_audio_ffmpeg(video_path, output_audio_path)

def extract_audio_ffmpeg(video_path, output_audio_path):
    """
    Fallback extraction using direct ffmpeg command line execution.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",                   # Disable video
        "-acodec", "pcm_s16le",  # PCM 16-bit
        "-ar", "16000",          # 16kHz sampling rate
        "-ac", "1",              # 1 channel (mono)
        output_audio_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print("[Audio] Audio extraction via FFmpeg subprocess completed successfully.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        err_msg = ""
        if isinstance(e, subprocess.CalledProcessError):
            err_msg = e.stderr.decode('utf-8', errors='ignore')
        else:
            err_msg = "FFmpeg executable not found in PATH."
        raise RuntimeError(f"Failed to extract audio using FFmpeg fallback. Error: {err_msg}")

def chunk_audio_vad(audio_path, output_dir, min_chunk_len=20.0, max_chunk_len=30.0, energy_threshold=0.015, silence_duration=0.5):
    """
    Reads the 16kHz WAV file block-by-block (memory-safe).
    Detects low-energy segments (silences) to split the audio into natural conversational chunks.
    Guarantees that each chunk is between min_chunk_len and max_chunk_len seconds.
    
    If a chunk reaches max_chunk_len without a silence, it splits at the point of minimum energy
    in the last 10 seconds to avoid cutting off speech mid-word.
    
    Returns:
        List of dicts: [
            {"path": "path/to/chunk.wav", "start": start_sec, "end": end_sec},
            ...
        ]
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    sample_rate = 16000
    block_len_sec = 0.1 # 100ms blocks
    block_samples = int(sample_rate * block_len_sec)
    
    # Calculate how many consecutive silent blocks represent a natural silence gap
    silence_blocks_needed = int(silence_duration / block_len_sec)
    
    chunks = []
    
    print(f"[VAD] Splitting '{audio_path}' into natural {min_chunk_len}-{max_chunk_len}s chunks...")
    
    with sf.SoundFile(audio_path) as f:
        # Verify sample rate
        file_sr = f.samplerate
        if file_sr != sample_rate:
            # We assume it is 16000 because extract_audio forces 16000Hz, but just in case:
            block_samples = int(file_sr * block_len_sec)
            sample_rate = file_sr
            silence_blocks_needed = int(silence_duration / block_len_sec)

        current_chunk_blocks = []
        consecutive_silence = 0
        
        # We read file block by block
        block_idx = 0
        total_blocks = len(f) // block_samples
        
        # Keep track of sample boundaries on the global timeline
        chunk_start_time = 0.0
        
        while True:
            # Read block
            block = f.read(block_samples, dtype='float32')
            if len(block) == 0:
                break
                
            # Compute RMS energy of block
            rms = np.sqrt(np.mean(block ** 2)) if len(block) > 0 else 0.0
            is_silent = rms < energy_threshold
            
            # Append block
            current_chunk_blocks.append((block, rms))
            block_idx += 1
            
            # Track silence hangover
            if is_silent:
                consecutive_silence += 1
            else:
                consecutive_silence = 0
                
            current_chunk_len = len(current_chunk_blocks) * block_len_sec
            
            # Check for natural split point:
            # We have seen enough silence, AND current chunk is long enough
            is_natural_split = (consecutive_silence >= silence_blocks_needed) and (current_chunk_len >= min_chunk_len)
            
            # Check for forced split point:
            # Chunk is too long and needs to be capped
            is_forced_split = current_chunk_len >= max_chunk_len
            
            if is_natural_split or is_forced_split:
                split_idx = len(current_chunk_blocks)
                
                # If we are forced to split, find the block with the lowest energy in the last 10 seconds of blocks
                if is_forced_split and not is_natural_split:
                    lookback_blocks = int(10.0 / block_len_sec)
                    lookback_start = max(0, len(current_chunk_blocks) - lookback_blocks)
                    
                    # Find block with min energy in the lookback window
                    min_energy_idx = lookback_start
                    min_energy = float('inf')
                    for idx in range(lookback_start, len(current_chunk_blocks)):
                        _, b_rms = current_chunk_blocks[idx]
                        if b_rms < min_energy:
                            min_energy = b_rms
                            min_energy_idx = idx
                            
                    # Split at the minimum energy block
                    split_idx = min_energy_idx + 1
                
                # Extract blocks for the new chunk
                chunk_blocks = current_chunk_blocks[:split_idx]
                remaining_blocks = current_chunk_blocks[split_idx:]
                
                # Stitch blocks together
                chunk_data = np.concatenate([b[0] for b in chunk_blocks])
                chunk_end_time = chunk_start_time + len(chunk_data) / sample_rate
                
                # Save chunk to disk
                chunk_filename = f"chunk_{len(chunks):04d}_{chunk_start_time:.2f}_{chunk_end_time:.2f}.wav"
                chunk_filepath = os.path.join(output_dir, chunk_filename)
                sf.write(chunk_filepath, chunk_data, sample_rate, subtype='PCM_16')
                
                chunks.append({
                    "path": chunk_filepath,
                    "start": chunk_start_time,
                    "end": chunk_end_time
                })
                
                # Prepare for next chunk
                current_chunk_blocks = remaining_blocks
                chunk_start_time = chunk_end_time
                consecutive_silence = 0
                
        # Write any leftover blocks at the end of the file
        if current_chunk_blocks:
            chunk_data = np.concatenate([b[0] for b in current_chunk_blocks])
            chunk_end_time = chunk_start_time + len(chunk_data) / sample_rate
            chunk_filename = f"chunk_{len(chunks):04d}_{chunk_start_time:.2f}_{chunk_end_time:.2f}.wav"
            chunk_filepath = os.path.join(output_dir, chunk_filename)
            sf.write(chunk_filepath, chunk_data, sample_rate, subtype='PCM_16')
            chunks.append({
                "path": chunk_filepath,
                "start": chunk_start_time,
                "end": chunk_end_time
            })
            
    print(f"[VAD] Completed splitting. Generated {len(chunks)} audio chunks.")
    return chunks
