"""
Implementation of the quality metrics calculator node for the EncodEx workflow.

This node calculates objective quality metrics (VMAF, PSNR) for test encodings
by comparing them to the original source video.
"""

import json
import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

from encodex.graph_state import EncodExState, QualityMetric


def _run_ffmpeg_command(cmd: List[str]) -> Tuple[bool, str]:
    """
    Run an FFmpeg command and return success status and output.

    Args:
        cmd: FFmpeg command as a list of strings

    Returns:
        Tuple of (success_status, output_or_error)
    """
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, f"FFmpeg error: {e.stderr}"


def _calculate_vmaf(
    test_encoding_path: str, original_video_path: str, start_time: float, duration: float
) -> Optional[Dict]:
    """
    Calculate VMAF score for a test encoding compared to the original.

    Args:
        test_encoding_path: Path to the test encoding file
        original_video_path: Path to the original video file
        start_time: Start time of the segment in seconds
        duration: Duration of the segment in seconds

    Returns:
        Dictionary with VMAF scores if successful, None otherwise
    """
    # Create temporary file for JSON output
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
        output_json = tmp_file.name

    try:
        # Build FFmpeg command for VMAF calculation
        cmd = [
            "ffmpeg",
            "-i",
            test_encoding_path,  # Distorted video (test encoding)
            "-ss",
            str(start_time),  # Start time for original video
            "-t",
            str(duration),  # Duration for original video
            "-i",
            original_video_path,  # Reference video (original)
            "-filter_complex",
            "[0:v]scale=1920:1080:flags=bicubic[distorted];"
            "[1:v]scale=1920:1080:flags=bicubic[reference];"
            "[distorted][reference]libvmaf=log_fmt=json:log_path=" + output_json,
            "-f",
            "null",
            "-",
        ]

        # Run FFmpeg command
        success, output = _run_ffmpeg_command(cmd)
        if not success:
            print(f"VMAF calculation failed: {output}")
            return None

        # Parse VMAF JSON output
        with open(output_json, "r") as f:
            vmaf_data = json.load(f)

        # Extract VMAF score
        vmaf_score = vmaf_data.get("pooled_metrics", {}).get("vmaf", {}).get("mean", None)

        # Get PSNR if available
        psnr_y = vmaf_data.get("pooled_metrics", {}).get("psnr_y", {}).get("mean", None)

        return {"vmaf": vmaf_score, "psnr": psnr_y}

    except Exception as e:
        print(f"Error calculating VMAF: {str(e)}")
        return None
    finally:
        # Clean up temporary file
        if os.path.exists(output_json):
            os.remove(output_json)


def _extract_segment_time_range(segment_id: str) -> Tuple[float, float]:
    """
    Extract start time and end time from segment ID.

    Args:
        segment_id: Segment ID in the format "start_time-end_time"

    Returns:
        Tuple of (start_time, duration)
    """
    try:
        parts = segment_id.split("-")
        start_time = float(parts[0])
        end_time = float(parts[1])
        duration = end_time - start_time
        return start_time, duration
    except (IndexError, ValueError) as e:
        print(f"Error parsing segment ID '{segment_id}': {str(e)}")
        return 0.0, 0.0


def calculate_quality_metrics(state: EncodExState) -> EncodExState:
    """
    Calculates quality metrics for test encodings.

    Args:
        state: Current workflow state

    Returns:
        Updated workflow state with quality metrics
    """
    if not state.test_encodings:
        state.error = "No test encodings available for quality metrics calculation"
        return state

    # Initialize quality metrics list
    state.quality_metrics = []

    # Calculate quality metrics for each test encoding
    for encoding in state.test_encodings:
        # Extract segment time range
        start_time, duration = _extract_segment_time_range(encoding.segment)

        # Skip if we couldn't parse the segment ID
        if duration <= 0:
            print(f"Skipping quality metrics for encoding with invalid segment ID: {encoding.segment}")
            continue

        # Calculate VMAF and PSNR
        metrics = _calculate_vmaf(
            test_encoding_path=encoding.path,
            original_video_path=state.input_file,
            start_time=start_time,
            duration=duration,
        )

        # Skip if metrics calculation failed
        if not metrics:
            print(f"Skipping quality metrics for encoding {encoding.path} due to calculation failure")
            continue

        # Create quality metric object
        quality_metric = QualityMetric(
            encoding_id=os.path.basename(encoding.path), vmaf=metrics["vmaf"], psnr=metrics["psnr"]
        )

        # Add to quality metrics list
        state.quality_metrics.append(quality_metric)

    # Check if we successfully calculated any quality metrics
    if not state.quality_metrics:
        state.error = "Failed to calculate quality metrics for any test encoding"

    return state
