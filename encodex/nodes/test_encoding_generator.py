"""
Implementation of the test encodings generator node for the EncodEx workflow.

This node generates test encodings for selected video segments using different
encoding parameters to evaluate quality vs. bitrate tradeoffs.
"""

import logging
import os
import platform  # Add platform import
import re  # Add re import for parsing progress
import subprocess
import sys  # Add sys import for stdout flushing
from typing import List, Optional

from encodex.graph_state import EnCodexState, TestEncoding

logger = logging.getLogger(__name__)


def _run_ffmpeg_command(cmd: List[str], duration_s: float) -> Optional[str]:
    """
    Run an FFmpeg command, print progress, and return error message if failed.

    Args:
        cmd: FFmpeg command as a list of strings. Must include '-progress pipe:1'.
        duration_s: Duration of the input segment in seconds for progress calculation.

    Returns:
        Error message if command failed, None otherwise.
    """
    logger.info(f"Executing FFmpeg command: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,  # Capture progress from stdout
        stderr=subprocess.PIPE,  # Capture errors from stderr
        text=True,  # Decode output as text
        encoding="utf-8",  # Specify encoding
        bufsize=1,  # Line buffered
    )

    total_duration_us = duration_s * 1000000 if duration_s > 0 else None
    # last_progress_line = "" # Removed unused variable

    # Read progress from stdout
    while True:
        if process.stdout is None:
            break
        line = process.stdout.readline()
        if not line:
            break

        # Simple parsing for 'out_time_us' (microseconds)
        match = re.search(r"out_time_us=(\d+)", line)
        # Ensure total_duration_us is valid (positive) before calculating progress
        if match and total_duration_us and total_duration_us > 0:
            current_us = int(match.group(1))
            progress = min(100.0, (current_us / total_duration_us) * 100)  # Cap at 100%
            # Print progress on the same line
            progress_line = f"\rProgress: {progress:.1f}%"
            print(progress_line, end="")
            # last_progress_line = progress_line # No longer needed for clearing
            sys.stdout.flush()  # Ensure it prints immediately
        # Removed explicit handling of 'progress=end' within the loop

    # Wait for the process to finish and capture remaining output/errors
    stdout, stderr = process.communicate()

    # Clear the progress line after the process completes
    # Use a sufficiently long string of spaces to ensure overwriting
    print("\r" + " " * 80 + "\r", end="")
    sys.stdout.flush()
    print()  # Add a newline for subsequent logs

    if process.returncode != 0:
        error_message = f"FFmpeg error (Exit Code {process.returncode}): {stderr.strip()}"
        logger.debug(error_message)  # Log the detailed error at debug level
        return error_message
    else:
        return None  # Success


def _create_test_encoding(  # noqa: PLR0913 Too many arguments
    input_file: str,
    segment: dict,
    resolution: str,
    bitrate: int,
    output_dir: str,
    use_gpu: bool = False,
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
    segment_id = f"{segment['start_time']:.2f}-{segment['end_time']:.2f}"
    logger.info(f"Creating test encoding for segment {segment_id} at {resolution} {bitrate}k...")

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Parse resolution
    width, height = resolution.split("x")

    # Generate output filename based on parameters
    output_filename = f"test_encoding_{segment_id}_{resolution}_{bitrate}k.mp4"
    output_path = os.path.join(output_dir, output_filename)
    logger.debug(f"Output path: {output_path}")

    # Calculate maxrate and bufsize (standard practice)
    maxrate = int(bitrate * 1.5)
    bufsize = bitrate * 2

    # Calculate segment duration for progress
    segment_duration = segment["end_time"] - segment["start_time"]

    # Base FFmpeg command parts
    base_cmd = [
        "ffmpeg",
        "-progress",
        "pipe:1",
        "-i",
        input_file,
        "-ss",
        str(segment["start_time"]),
        "-to",
        str(segment["end_time"]),
    ]

    # Video codec specific parts
    encoder_cmd = []
    if use_gpu and platform.system() == "Darwin":
        logger.info("Attempting to use hardware encoder (h264_videotoolbox)...")
        encoder_cmd = [
            "-c:v",
            "h264_videotoolbox",
            "-allow_sw",
            "1",  # Enable software fallback
            "-b:v",
            f"{bitrate}k",
            "-maxrate",
            f"{maxrate}k",  # Maxrate is supported
            # Bufsize might not be directly applicable or behave differently
            # Preset is not applicable
        ]
    else:
        if use_gpu and platform.system() != "Darwin":
            logger.warning(
                "GPU acceleration requested, but only macOS VideoToolbox is currently supported. Falling back to CPU."
            )
        logger.info("Using CPU encoder (libx264)...")
        encoder_cmd = [
            "-c:v",
            "libx264",
            "-b:v",
            f"{bitrate}k",
            "-maxrate",
            f"{maxrate}k",
            "-bufsize",
            f"{bufsize}k",
            "-preset",
            "slow",  # Higher quality encoding for tests
        ]

    # Scaling and output parts
    output_cmd = [
        "-vf",
        f"scale={width}:{height}",
        "-an",  # No audio needed for test segments
        "-y",  # Overwrite existing files
        output_path,
    ]

    # Combine command parts
    final_cmd = base_cmd + encoder_cmd + output_cmd

    # Run FFmpeg command and capture potential error
    error_message = _run_ffmpeg_command(final_cmd, segment_duration)

    if error_message:  # Check if an error message string was returned
        # Progress line clearing is now handled within _run_ffmpeg_command after communicate()
        logger.error(
            f"Failed to create test encoding for segment {segment_id} ({resolution} {bitrate}k): {error_message}"
        )
        return None
    else:
        logger.info(f"Successfully created test encoding: {output_path}")

    # Return TestEncoding object
    return TestEncoding(path=output_path, resolution=resolution, bitrate=bitrate, segment=segment_id)


def generate_test_encodings(state: EnCodexState, use_gpu: bool = False) -> EnCodexState:
    """
    Generates test encodings for selected segments.

    Args:
        state: Current workflow state
        use_gpu: If True and on macOS, attempt to use the VideoToolbox hardware encoder.
                 Defaults to False (uses libx264 CPU encoder).

    Returns:
        Updated workflow state with test encodings
    """
    logger.info("Starting test encoding generation...")
    if not state.selected_segments:
        logger.warning("No segments selected for test encoding.")
        state.error = "No segments selected for test encoding"
        return state

    logger.info(f"Found {len(state.selected_segments)} segments selected for encoding.")

    # Set up output directory for test encodings
    output_dir = os.path.join(os.path.dirname(state.input_file), "test_encodings")
    logger.info(f"Output directory for test encodings: {output_dir}")

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
        segment_id = f"{segment.start_time:.2f}-{segment.end_time:.2f}"
        logger.info(f"Processing segment {segment_id} with complexity: {segment.complexity}")

        # Get encoding parameters based on segment complexity
        # Default to Medium if complexity is not recognized
        complexity = segment.complexity
        if complexity not in encoding_params:
            logger.warning(
                f"Complexity '{complexity}' not recognized for segment {segment_id}. Defaulting to 'Medium'."
            )
            complexity = "Medium"

        params_to_use = encoding_params[complexity]
        logger.debug(f"Using parameters for '{complexity}' complexity: {params_to_use}")

        # Generate test encodings for this segment
        for params in encoding_params[complexity]:
            encoding = _create_test_encoding(
                input_file=state.input_file,
                segment=segment_data,
                resolution=params["resolution"],
                bitrate=params["bitrate"],
                output_dir=output_dir,
                use_gpu=use_gpu,  # Pass the flag down
            )

            if encoding:
                state.test_encodings.append(encoding)
            else:
                # Error already logged in _create_test_encoding
                logger.warning(
                    f"Skipping failed encoding for segment {segment_id} ({params['resolution']} {params['bitrate']}k)"
                )

    # Check if we successfully created any test encodings
    if not state.test_encodings:
        logger.error("Failed to create any test encodings.")
        state.error = "Failed to create any test encodings"
    else:
        logger.info(f"Successfully generated {len(state.test_encodings)} test encodings.")

    return state
