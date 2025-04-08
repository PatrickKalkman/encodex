"""
Implementation of the quality metrics calculator node for the EncodEx workflow.

This node calculates objective quality metrics (VMAF, PSNR) for test encodings
by comparing them to the original source video.
"""

import json
import logging
import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

from encodex.graph_state import EncodExState, QualityMetric

# Set up logger
logger = logging.getLogger(__name__)


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
        return True, result.stdout + result.stderr  # Combine stdout and stderr to catch all output
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
        # Build FFmpeg command for VMAF calculation with explicit scaling
        # The error shows we need to ensure both videos are at the same resolution
        cmd = [
            "ffmpeg",
            "-i",
            test_encoding_path,
            "-ss",
            str(start_time),
            "-t",
            str(duration),
            "-i",
            original_video_path,
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
            logger.warning(f"VMAF calculation failed: {output}")
            return None

        # Parse VMAF JSON output
        with open(output_json, "r") as f:
            vmaf_data = json.load(f)

        # Extract VMAF score
        vmaf_score = None
        if "pooled_metrics" in vmaf_data and "vmaf" in vmaf_data["pooled_metrics"]:
            vmaf_score = vmaf_data["pooled_metrics"]["vmaf"].get("mean", None)

        # Return VMAF score
        if vmaf_score is not None:
            return {"vmaf": vmaf_score}
        else:
            logger.warning("Could not find VMAF score in output")
            return None

    except Exception as e:
        logger.error(f"Error calculating VMAF: {str(e)}")
        return None
    finally:
        # Clean up temporary file
        if os.path.exists(output_json):
            os.remove(output_json)


def _calculate_psnr(
    test_encoding_path: str, original_video_path: str, start_time: float, duration: float
) -> Optional[float]:
    """
    Calculate PSNR score for a test encoding compared to the original.

    Args:
        test_encoding_path: Path to the test encoding file
        original_video_path: Path to the original video file
        start_time: Start time of the segment in seconds
        duration: Duration of the segment in seconds

    Returns:
        PSNR value if successful, None otherwise
    """
    try:
        # Build FFmpeg command for PSNR calculation with explicit scaling
        cmd = [
            "ffmpeg",
            "-i",
            test_encoding_path,
            "-ss",
            str(start_time),
            "-t",
            str(duration),
            "-i",
            original_video_path,
            "-filter_complex",
            "[0:v]scale=1920:1080:flags=bicubic[distorted];"
            "[1:v]scale=1920:1080:flags=bicubic[reference];"
            "[distorted][reference]psnr",
            "-f",
            "null",
            "-",
        ]

        # Run FFmpeg command
        success, output = _run_ffmpeg_command(cmd)
        if not success:
            logger.warning(f"PSNR calculation failed: {output}")
            return None

        # Parse PSNR from FFmpeg output
        # Look for the average PSNR line in FFmpeg output
        psnr_avg = None
        for line in output.split("\n"):
            if "PSNR" in line and "average" in line:
                try:
                    # Format is typically: [Parsed_psnr_0 @ 0x...] PSNR average:27.31 min:24.22 max:31.58
                    parts = line.split("average:")[1].strip().split(" ")
                    psnr_avg = float(parts[0])
                    break
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse PSNR from line: {line}, error: {e}")

        return psnr_avg

    except Exception as e:
        logger.error(f"Error calculating PSNR: {str(e)}")
        return None


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
        logger.error(f"Error parsing segment ID '{segment_id}': {str(e)}")
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
        logger.error(state.error)
        return state

    # Initialize quality metrics list
    state.quality_metrics = []

    logger.info("Starting quality metrics calculation node.")
    logger.info(f"Found {len(state.test_encodings)} test encodings to process.")

    # Calculate quality metrics for each test encoding
    for i, encoding in enumerate(state.test_encodings, 1):
        # Log progress
        logger.info(f"Processing encoding {i}/{len(state.test_encodings)}: {encoding.path}")

        # Extract segment time range
        start_time, duration = _extract_segment_time_range(encoding.segment)

        # Skip if we couldn't parse the segment ID
        if duration <= 0:
            logger.warning(f"Skipping quality metrics for encoding with invalid segment ID: {encoding.segment}")
            continue

        # Calculate VMAF
        logger.info(f"Calculating VMAF for {os.path.basename(encoding.path)} (segment {encoding.segment})")
        vmaf_result = _calculate_vmaf(
            test_encoding_path=encoding.path,
            original_video_path=state.input_file,
            start_time=start_time,
            duration=duration,
        )

        # Skip if VMAF calculation failed
        if not vmaf_result:
            logger.error(f"Failed to calculate VMAF for {os.path.basename(encoding.path)}")
            continue

        # Calculate PSNR separately
        logger.info(f"Calculating PSNR for {os.path.basename(encoding.path)} (segment {encoding.segment})")
        psnr_value = _calculate_psnr(
            test_encoding_path=encoding.path,
            original_video_path=state.input_file,
            start_time=start_time,
            duration=duration,
        )

        # Use -1.0 as fallback if PSNR calculation failed
        if psnr_value is None:
            logger.warning(f"Using default PSNR value for {os.path.basename(encoding.path)}")
            psnr_value = -1.0

        # Log results
        logger.info(
            f"Calculated metrics for {os.path.basename(encoding.path)}: VMAF={vmaf_result['vmaf']:.2f}, PSNR={psnr_value:.2f}"
        )

        # Create quality metric object
        quality_metric = QualityMetric(
            encoding_id=os.path.basename(encoding.path), vmaf=vmaf_result["vmaf"], psnr=psnr_value
        )

        # Add to quality metrics list
        state.quality_metrics.append(quality_metric)

    # Check if we successfully calculated any quality metrics
    if not state.quality_metrics:
        state.error = "Failed to calculate quality metrics for any test encoding"
        logger.error(state.error)
    else:
        logger.info(f"Successfully calculated quality metrics for {len(state.quality_metrics)} encodings.")

    logger.info("Finished quality metrics calculation node.")
    return state
