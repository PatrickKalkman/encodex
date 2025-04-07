"""
Implementation of the test encodings generator node for the EncodEx workflow.

This node generates test encodings for selected video segments using different
encoding parameters to evaluate quality vs. bitrate tradeoffs.
"""

import os
import subprocess
from typing import List, Optional

from encodex.graph_state import EncodExState, TestEncoding


def _run_ffmpeg_command(cmd: List[str]) -> Optional[str]:
    """
    Run an FFmpeg command and return error message if failed.

    Args:
        cmd: FFmpeg command as a list of strings

    Returns:
        Error message if command failed, None otherwise
    """
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result
    except subprocess.CalledProcessError as e:
        return f"FFmpeg error: {e.stderr}"


def _create_test_encoding(
    input_file: str, segment: dict, resolution: str, bitrate: int, output_dir: str
) -> Optional[TestEncoding]:
    """
    Create a test encoding for a specific segment with given parameters.

    Args:
        input_file: Path to the original video file
        segment: Segment dict with start_time and end_time
        resolution: Resolution as WIDTHxHEIGHT string
        bitrate: Target bitrate in kbps
        output_dir: Directory to store output files

    Returns:
        TestEncoding object if successful, None if failed
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Parse resolution
    width, height = resolution.split("x")

    # Generate output filename based on parameters
    segment_id = f"{segment['start_time']:.2f}-{segment['end_time']:.2f}"
    output_filename = f"test_encoding_{segment_id}_{resolution}_{bitrate}k.mp4"
    output_path = os.path.join(output_dir, output_filename)

    # Calculate maxrate and bufsize (standard practice)
    maxrate = int(bitrate * 1.5)
    bufsize = bitrate * 2

    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-i",
        input_file,
        "-ss",
        str(segment["start_time"]),
        "-to",
        str(segment["end_time"]),
        "-c:v",
        "libx264",
        "-b:v",
        f"{bitrate}k",
        "-maxrate",
        f"{maxrate}k",
        "-bufsize",
        f"{bufsize}k",
        "-vf",
        f"scale={width}:{height}",
        "-preset",
        "slow",  # Higher quality encoding for tests
        "-an",  # No audio needed for test segments
        "-y",  # Overwrite existing files
        output_path,
    ]

    # Run FFmpeg command
    error = _run_ffmpeg_command(cmd)
    if error:
        print(f"Failed to create test encoding: {error}")
        return None

    # Return TestEncoding object
    return TestEncoding(path=output_path, resolution=resolution, bitrate=bitrate, segment=segment_id)


def generate_test_encodings(state: EncodExState) -> EncodExState:
    """
    Generates test encodings for selected segments.

    Args:
        state: Current workflow state

    Returns:
        Updated workflow state with test encodings
    """
    if not state.selected_segments:
        state.error = "No segments selected for test encoding"
        return state

    # Set up output directory for test encodings
    output_dir = os.path.join(os.path.dirname(state.input_file), "test_encodings")

    # Initialize test encodings list
    state.test_encodings = []

    # Define test encoding parameters based on Apple's encoding ladder
    # Using a targeted subset based on complexity categories
    encoding_params = {
        "Low": [
            # For low complexity, test with lower resolutions and bitrates
            {"resolution": "640x360", "bitrate": 365},
            {"resolution": "960x540", "bitrate": 2000},
            {"resolution": "1280x720", "bitrate": 3000},
        ],
        "Medium": [
            # For medium complexity, use mid-tier resolutions and bitrates
            {"resolution": "768x432", "bitrate": 730},
            {"resolution": "960x540", "bitrate": 2000},
            {"resolution": "1280x720", "bitrate": 4500},
        ],
        "High": [
            # For high complexity, focus on higher resolutions and bitrates
            {"resolution": "960x540", "bitrate": 2000},
            {"resolution": "1280x720", "bitrate": 4500},
            {"resolution": "1920x1080", "bitrate": 6000},
        ],
        "Ultra-high": [
            # For ultra-high complexity content
            {"resolution": "1280x720", "bitrate": 4500},
            {"resolution": "1920x1080", "bitrate": 6000},
            {"resolution": "1920x1080", "bitrate": 7800},
        ],
    }

    # Process each selected segment
    for segment in state.selected_segments:
        # Extract the segment data we need
        segment_data = {
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "complexity": segment.complexity,
        }

        # Get encoding parameters based on segment complexity
        # Default to Medium if complexity is not recognized
        complexity = segment.complexity
        if complexity not in encoding_params:
            complexity = "Medium"

        # Generate test encodings for this segment
        for params in encoding_params[complexity]:
            encoding = _create_test_encoding(
                input_file=state.input_file,
                segment=segment_data,
                resolution=params["resolution"],
                bitrate=params["bitrate"],
                output_dir=output_dir,
            )

            if encoding:
                state.test_encodings.append(encoding)

    # Check if we successfully created any test encodings
    if not state.test_encodings:
        state.error = "Failed to create any test encodings"

    return state
