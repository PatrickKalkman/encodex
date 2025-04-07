"""
Input processor node for validating and extracting metadata from video files.
"""

import json
import os
import subprocess

from encodex.graph_state import EncodExState, VideoMetadata


def process_input(state: EncodExState) -> EncodExState:
    """
    Process the input video file:
    - Validate that it exists and is a supported format
    - Extract metadata using FFmpeg
    - Update state with metadata

    Args:
        state: Current graph state with input_file path

    Returns:
        Updated state with video metadata

    Raises:
        ValueError: If input file is invalid or unsupported
    """
    input_file = state.input_file

    # Validate input file
    if not os.path.exists(input_file):
        state.error = f"Input file does not exist: {input_file}"
        return state

    # Get file extension
    _, ext = os.path.splitext(input_file)
    if ext.lower() not in [".mp4", ".mov", ".mkv", ".avi"]:
        state.error = f"Unsupported file format: {ext}. Supported formats: .mp4, .mov, .mkv, .avi"
        return state

    # Extract metadata using FFmpeg
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_file]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            state.error = f"Failed to extract metadata: {result.stderr}"
            return state

        metadata = json.loads(result.stdout)

        # Find video stream
        video_stream = None
        for stream in metadata.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            state.error = "No video stream found in input file"
            return state

        # Extract relevant metadata
        duration = float(metadata.get("format", {}).get("duration", 0))
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        # Calculate framerate from fraction if present
        fps = None
        frame_rate = video_stream.get("r_frame_rate")
        if frame_rate:
            try:
                num, denom = map(int, frame_rate.split("/"))
                fps = num / denom if denom else None
            except (ValueError, ZeroDivisionError):
                fps = None

        # Get video codec
        codec = video_stream.get("codec_name")

        # Try to get bitrate
        bitrate = None
        try:
            bitrate = int(metadata.get("format", {}).get("bit_rate", 0))
        except (ValueError, TypeError):
            pass

        # Create video metadata
        video_metadata = VideoMetadata(
            path=input_file, duration=duration, width=width, height=height, fps=fps, codec=codec, bitrate=bitrate
        )

        # Update state
        state.video_metadata = video_metadata

        return state

    except Exception as e:
        state.error = f"Error processing input file: {str(e)}"
        return state
