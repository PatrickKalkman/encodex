"""
Video splitter node for splitting videos into smaller chunks for processing by Gemini.
"""

import json
import os
import subprocess

from encodex.graph_state import EnCodexState


def split_video(state: EnCodexState) -> EnCodexState:
    """
    Split a video into smaller chunks for Gemini processing.

    Args:
        state: Current graph state with low_res_path

    Returns:
        Updated state with chunk_paths added
    """
    # Validate input
    if not state.low_res_path or not os.path.exists(state.low_res_path):
        state.error = "Missing or invalid low-resolution video path"
        return state

    try:
        # Default max size for Gemini is 50MB
        max_size_mb = 50

        # Get input file path
        low_res_path = state.low_res_path

        # Get file size in bytes
        file_size = os.path.getsize(low_res_path)
        file_size_mb = file_size / (1024 * 1024)

        # If file is already small enough, return it as is
        if file_size_mb <= max_size_mb:
            # Just store the path as is
            state.chunk_paths = [low_res_path]
            return state

        # Get video duration
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", low_res_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            state.error = f"FFprobe error: {result.stderr}"
            return state

        metadata = json.loads(result.stdout)
        duration = float(metadata.get("format", {}).get("duration", 0))

        if duration <= 0:
            state.error = "Could not determine video duration"
            return state

        # Calculate number of chunks needed
        # Add 10% buffer to account for keyframe alignment and overhead
        num_chunks = int((file_size_mb / max_size_mb) * 1.1) + 1

        # Calculate chunk duration
        chunk_duration = duration / num_chunks

        # Create output directory if needed
        base_path = os.path.dirname(low_res_path)
        filename = os.path.basename(low_res_path)
        name, ext = os.path.splitext(filename)

        # Create chunks
        chunks = []
        # Initialize the dictionary in the state
        state.chunk_start_times = {}  # Ensure it's empty before starting

        for i in range(num_chunks):
            start_time = i * chunk_duration  # This is the offset we need
            output_path = os.path.join(base_path, f"{name}_{i + 1:03d}{ext}")

            cmd = [
                "ffmpeg",
                "-y",  # Overwrite existing files
                "-i",
                low_res_path,
                "-ss",
                str(start_time),  # Start time
                "-t",
                str(chunk_duration),  # Duration
                "-c",
                "copy",  # Copy codecs (fast)
                output_path,
            ]

            print(f"Creating chunk {i + 1}/{num_chunks}: {output_path} (starts at {start_time:.2f}s)")  # Log start time
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"Warning: Error creating chunk {i + 1}: {result.stderr}")
                continue

            # Verify file was created and is not empty
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                chunks.append(output_path)
                # Store the start time for this chunk
                state.chunk_start_times[output_path] = start_time
            else:
                print(f"Warning: Chunk {i + 1} was not created or is empty")

        if not chunks:
            state.error = "Failed to create any valid chunks"
            return state

        # Update state with chunk paths
        state.chunk_paths = chunks

        return state

    except Exception as e:
        state.error = f"Error splitting video: {str(e)}"
        return state
