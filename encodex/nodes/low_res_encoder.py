"""
Low-resolution encoder node for creating a preview version of the video for analysis.
"""

import json
import os
import platform
import re  # Add re import for parsing progress
import subprocess
import sys  # Add sys import for stdout flushing

from encodex.graph_state import EncodExState


def create_low_res_preview(state: EncodExState, use_gpu: bool = False) -> EncodExState:
    """
    Create a low-resolution preview of the input video for analysis:
    - Generate a 240p low-bitrate version of the video
    - Use FFmpeg with efficient settings for quick encoding (CPU or GPU)
    - Update state with the path to the low-res preview

    Args:
        state: Current graph state with input file and metadata
        use_gpu: If True and on macOS, attempt to use the VideoToolbox hardware encoder.
                 Defaults to False (uses libx264 CPU encoder).

    Returns:
        Updated state with low_res_path

    Raises:
        ValueError: If input file is missing or invalid
    """
    # Validate input
    if not state.video_metadata or not state.video_metadata.path:
        state.error = "Missing video metadata or path"
        return state

    input_file = state.video_metadata.path

    # Create output directory if it doesn't exist
    output_dir = os.path.join(os.path.dirname(input_file), "encodex_temp")
    os.makedirs(output_dir, exist_ok=True)

    # Generate output filename
    input_basename = os.path.basename(input_file)
    name, ext = os.path.splitext(input_basename)
    low_res_path = os.path.join(output_dir, f"{name}_240p_preview{ext}")

    # Build FFmpeg command
    try:
        base_cmd = [
            "ffmpeg",
            "-y",  # Overwrite output file if it exists
            "-i",
            input_file,
            "-vf",
            "scale=trunc(oh*a/2)*2:240",  # Scale to 240p ensuring even width
        ]

        # Add progress reporting to stdout
        progress_cmd = ["-progress", "pipe:1"]

        encoder_cmd = []
        # Use VideoToolbox on macOS if requested
        if use_gpu and platform.system() == "Darwin":
            print("Attempting to use hardware encoder (h264_videotoolbox)...")
            encoder_cmd = [
                "-c:v",
                "h264_videotoolbox",
                "-b:v",
                "500k",  # Target bitrate for low-res preview
                "-allow_sw", "1", # Enable software fallback (provide value '1')
                # Note: '-crf' and '-preset' are not typically used with videotoolbox
            ]
        else:
            # Default to libx264 CPU encoding
            # Using settings from spec (section 11.2):
            # ffmpeg -i [INPUT] -vf scale=-1:240 -c:v libx264 -crf 23 -preset fast [OUTPUT]
            print("Using CPU encoder (libx264)...")
            encoder_cmd = [
                "-c:v",
                "libx264",  # Use H.264 codec
                "-crf",
                "23",  # Constant Rate Factor (balance quality/size)
                "-preset",
                "fast",  # Encoding speed preset
            ]

        # Combine command parts: base + progress + encoder + audio disable + output path
        final_cmd = base_cmd + progress_cmd + encoder_cmd + ["-an", low_res_path]

        # Run FFmpeg using Popen to capture progress
        print(f"Running FFmpeg command: {' '.join(final_cmd)}") # Keep this for debugging
        process = subprocess.Popen(
            final_cmd,
            stdout=subprocess.PIPE, # Capture progress from stdout
            stderr=subprocess.PIPE, # Capture errors from stderr
            text=True, # Decode output as text
            encoding='utf-8', # Specify encoding
            bufsize=1 # Line buffered
        )

        # Get total duration for percentage calculation
        total_duration_ms = None
        if state.video_metadata and state.video_metadata.duration:
            total_duration_ms = state.video_metadata.duration * 1000000 # Convert seconds to microseconds

        print("Encoding low-res preview...")
        # Read progress from stdout
        while True:
            if process.stdout is None:
                break
            line = process.stdout.readline()
            if not line:
                break

            # Simple parsing for 'out_time_ms'
            match = re.search(r"out_time_ms=(\d+)", line)
            if match and total_duration_ms:
                current_ms = int(match.group(1))
                progress = (current_ms / total_duration_ms) * 100
                # Print progress on the same line
                print(f"\rProgress: {progress:.1f}%", end="")
                sys.stdout.flush() # Ensure it prints immediately

        # Wait for the process to finish and capture remaining output/errors
        stdout, stderr = process.communicate()

        # Print final newline after progress updates
        print("\rEncoding complete.      ") # Overwrite progress line

        if process.returncode != 0:
            state.error = f"FFmpeg error (code {process.returncode}): {stderr}"
            return state

        # Check if output file exists
        if not os.path.exists(low_res_path):
            state.error = f"Failed to create low-res preview: {low_res_path}"
            return state

        # Update state
        state.low_res_path = low_res_path

        return state

    except Exception as e:
        state.error = f"Error creating low-res preview: {str(e)}"
        return state


def split_video_for_gemini(low_res_path: str, max_size_mb: int = 50) -> list:
    """
    Split the low-res video into chunks that are small enough for Gemini.

    Args:
        low_res_path: Path to the low-res video
        max_size_mb: Maximum size of each chunk in MB

    Returns:
        List of paths to the chunk files
    """
    # Get file size in bytes
    file_size = os.path.getsize(low_res_path)
    file_size_mb = file_size / (1024 * 1024)

    # If file is already small enough, return it as is
    if file_size_mb <= max_size_mb:
        return [low_res_path]

    # Calculate number of chunks needed
    num_chunks = int(file_size_mb / max_size_mb) + 1

    # Get video duration
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", low_res_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    duration = float(metadata.get("format", {}).get("duration", 0))

    # Calculate chunk duration
    chunk_duration = duration / num_chunks

    # Create chunks
    base_path, ext = os.path.splitext(low_res_path)
    chunks = []

    for i in range(num_chunks):
        start_time = i * chunk_duration
        output_path = f"{base_path}_{i + 1:03d}{ext}"

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            low_res_path,
            "-ss",
            str(start_time),
            "-t",
            str(chunk_duration),
            "-c",
            "copy",
            output_path,
        ]

        subprocess.run(cmd, capture_output=True)

        # Verify file was created
        if os.path.exists(output_path):
            chunks.append(output_path)

    return chunks
