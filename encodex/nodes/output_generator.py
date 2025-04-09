"""
Implementation of the output generator node for the EncodEx workflow.

This node creates the final JSON output with encoding recommendations and analysis.
"""

import json
import logging
import os
from typing import Any, Dict

from encodex.graph_state import EnCodexState

# Set up logger
logger = logging.getLogger(__name__)


def _create_output_json(state: EnCodexState) -> Dict[str, Any]:
    """
    Create the final JSON output structure.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with formatted output
    """
    # Extract input file name
    input_filename = os.path.basename(state.input_file)

    # Prepare metadata section
    metadata = {
        "duration": (
            f"{int(state.video_metadata.duration // 3600):02d}:{int((state.video_metadata.duration % 3600) // 60):02d}"
            ":{int(state.video_metadata.duration % 60):02d}"
        ),
        "original_resolution": f"{state.video_metadata.width}x{state.video_metadata.height}",
        "fps": state.video_metadata.fps,
    }

    # Prepare content analysis section
    content_analysis = {
        "complexity_category": state.complexity_category.value,
        "motion_intensity": int(state.content_analysis.motion_intensity.score),
        "spatial_complexity": int(state.content_analysis.spatial_complexity.score),
        "temporal_complexity": int(state.content_analysis.temporal_complexity.score),
        "scene_change_frequency": int(state.content_analysis.scene_change_frequency.score),
        "texture_detail": int(state.content_analysis.texture_detail_prevalence.score),
        "contrast_levels": int(state.content_analysis.contrast_levels.score),
        "animation_type": state.content_analysis.animation_type.type,
        "grain_noise_levels": int(state.content_analysis.grain_noise_levels.score),
    }

    # Prepare encoding ladder section
    encoding_ladder = []
    for params in state.encoding_ladder:
        encoding_ladder.append({"resolution": params.resolution, "bitrate": params.bitrate, "profile": params.profile})

    # Final output structure
    output = {
        "input_file": input_filename,
        "metadata": metadata,
        "content_analysis": content_analysis,
        "encoding_ladder": encoding_ladder,
        "baseline_comparison": {"estimated_savings": state.estimated_savings},
    }

    return output


def generate_output(state: EnCodexState) -> EnCodexState:
    """
    Generates the final output with encoding recommendations.

    Args:
        state: Current workflow state with encoding ladder

    Returns:
        Updated workflow state (no changes needed)
    """
    logger.info("Starting output generator node.")

    if not state.encoding_ladder:
        state.error = "Missing encoding ladder for output generation"
        logger.error(state.error)
        return state

    if not state.content_analysis:
        state.error = "Missing content analysis for output generation"
        logger.error(state.error)
        return state

    try:
        # Create the formatted output
        output_json = _create_output_json(state)

        # Log the output
        logger.info("Generated final output JSON:")
        logger.info(json.dumps(output_json, indent=2))

        # We don't need to modify the state since it already contains all
        # the necessary information. The output JSON would typically be
        # written to a file by the CLI or other external handler.

        logger.info("Output generator node finished.")
        return state

    except Exception as e:
        state.error = f"Error generating output: {str(e)}"
        logger.error(state.error)
        return state
