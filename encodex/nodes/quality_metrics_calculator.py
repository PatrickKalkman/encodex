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

logger = logging.getLogger(__name__)


def _run_ffmpeg_command(cmd: List[str]) -> Tuple[bool, str]:
    """
    Run an FFmpeg command and return success status and output.

    Args:
        cmd: FFmpeg command as a list of strings

    Returns:
        Tuple of (success_status, output_or_error)
    """
    logger.debug("Running FFmpeg command: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.debug("FFmpeg command successful. Stdout: %s", result.stdout)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg command failed. Stderr: %s", e.stderr)
        return False, f"FFmpeg error: {e.stderr}"
    except FileNotFoundError:
        logger.error("FFmpeg command not found. Make sure FFmpeg is installed and in the system PATH.")
        return False, "FFmpeg command not found."


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
    logger.info(
        "Calculating VMAF for %s (segment %s-%s)",
        os.path.basename(test_encoding_path),
        start_time,
        start_time + duration,
    )
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
            logger.error("VMAF calculation failed for %s: %s", test_encoding_path, output)
            return None

        # Parse VMAF JSON output
        logger.debug("Parsing VMAF JSON output from %s", output_json)
        with open(output_json) as f:
            vmaf_data = json.load(f)

        # Extract VMAF score
        vmaf_score = vmaf_data.get("pooled_metrics", {}).get("vmaf", {}).get("mean", None)

        # Get PSNR if available
        psnr_y = vmaf_data.get("pooled_metrics", {}).get("psnr_y", {}).get("mean", None)

        logger.info(
            "Calculated metrics for %s: VMAF=%.2f, PSNR=%.2f",
            os.path.basename(test_encoding_path),
            vmaf_score if vmaf_score is not None else -1.0,
            psnr_y if psnr_y is not None else -1.0,
        )
        return {"vmaf": vmaf_score, "psnr": psnr_y}

    except FileNotFoundError:
        logger.error("VMAF JSON file not found: %s", output_json)
        return None
    except json.JSONDecodeError:
        logger.error("Error decoding VMAF JSON from %s", output_json)
        return None
    except Exception as e:
        logger.exception("Unexpected error calculating VMAF for %s: %s", test_encoding_path, e)
        return None
    finally:
        # Clean up temporary file
        logger.debug("Cleaning up temporary VMAF JSON file: %s", output_json)
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
        logger.debug("Extracted time range from segment ID '%s': start=%.3f, duration=%.3f", segment_id, start_time, duration)
        return start_time, duration
    except (IndexError, ValueError, TypeError) as e:
        logger.error("Error parsing segment ID '%s': %s", segment_id, e)
        return 0.0, 0.0


def calculate_quality_metrics(state: EncodExState) -> EncodExState:
    """
    Calculates quality metrics for test encodings.

    Args:
        state: Current workflow state

    Returns:
        Updated workflow state with quality metrics
    """
    logger.info("Starting quality metrics calculation node.")
    if not state.input_file or not os.path.exists(state.input_file):
        logger.error("Input file path is missing or invalid in state.")
        state.error = "Input file path is missing or invalid for quality metrics calculation."
        return state

    if not state.test_encodings:
        logger.warning("No test encodings found in state. Skipping quality metrics calculation.")
        state.error = "No test encodings available for quality metrics calculation"
        # Return state without error if no encodings is not necessarily an error state?
        # Or maybe set a specific status? For now, keep the error.
        return state

    logger.info("Found %d test encodings to process.", len(state.test_encodings))

    # Initialize quality metrics list
    state.quality_metrics = []

    # Calculate quality metrics for each test encoding
    for i, encoding in enumerate(state.test_encodings):
        logger.info("Processing encoding %d/%d: %s", i + 1, len(state.test_encodings), encoding.path)

        if not encoding.path or not os.path.exists(encoding.path):
            logger.warning("Skipping encoding %d: Path '%s' is invalid or file does not exist.", i + 1, encoding.path)
            continue

        # Extract segment time range
        start_time, duration = _extract_segment_time_range(encoding.segment)

        # Skip if we couldn't parse the segment ID or duration is invalid
        if duration <= 0:
            logger.warning(
                "Skipping quality metrics for encoding %s: Invalid segment ID '%s' or non-positive duration.",
                encoding.path,
                encoding.segment,
            )
            continue

        # Calculate VMAF and PSNR
        logger.debug("Calculating metrics for encoding: %s, original: %s, start: %.3f, duration: %.3f",
                     encoding.path, state.input_file, start_time, duration)
        metrics = _calculate_vmaf(
            test_encoding_path=encoding.path,
            original_video_path=state.input_file,
            start_time=start_time,
            duration=duration,
        )

        # Skip if metrics calculation failed or returned None
        if metrics is None:
            logger.warning("Skipping quality metrics for encoding %s due to calculation failure or invalid result.", encoding.path)
            continue

        # Create quality metric object
        encoding_id = os.path.basename(encoding.path)
        vmaf_score = metrics.get("vmaf")
        psnr_score = metrics.get("psnr")

        if vmaf_score is None:
            logger.warning("VMAF score is None for encoding %s. Skipping metric entry.", encoding_id)
            continue # Or should we add with None? Depends on downstream requirements.

        quality_metric = QualityMetric(
            encoding_id=encoding_id,
            vmaf=vmaf_score,
            psnr=psnr_score # PSNR can be None if not available in VMAF output
        )
        logger.debug("Created QualityMetric: %s", quality_metric)

        # Add to quality metrics list
        state.quality_metrics.append(quality_metric)

    # Check if we successfully calculated any quality metrics
    if not state.quality_metrics:
        logger.warning("Failed to calculate quality metrics for any test encoding.")
        state.error = "Failed to calculate quality metrics for any test encoding"
    else:
        logger.info("Successfully calculated quality metrics for %d encodings.", len(state.quality_metrics))
        # Clear error if previously set and we have some results now
        if state.error == "Failed to calculate quality metrics for any test encoding":
             state.error = None

    logger.info("Finished quality metrics calculation node.")
    return state
