"""
Implementation of the data aggregator node for the EncodEx workflow.

This node aggregates content analysis and quality metrics data to determine the
overall complexity category and prepare data for recommendation generation.
"""

import logging
from typing import Dict, List, Tuple

from encodex.graph_state import ComplexityCategory, EnCodexState, QualityMetric

# Set up logger
logger = logging.getLogger(__name__)


def _calculate_bitrate_quality_curve(
    quality_metrics: List[QualityMetric], use_vmaf: bool = True
) -> Dict[str, Dict[int, float]]:
    """
    Calculate bitrate vs. quality curves for different resolutions.

    Args:
        quality_metrics: List of quality metrics
        use_vmaf: Whether to use VMAF (True) or PSNR (False) as quality metric

    Returns:
        Dictionary mapping resolutions to dictionaries of bitrate->quality
    """
    curves = {}

    # Extract resolution from encoding_id
    for metric in quality_metrics:
        # Parse encoding_id to extract resolution and bitrate
        try:
            parts = metric.encoding_id.split("_")
            # Format is test_encoding_START-END_WIDTHxHEIGHT_BITRATEk.mp4
            resolution_part = parts[-2]  # e.g., "1280x720"
            bitrate_part = parts[-1]  # e.g., "4500k.mp4"
            bitrate = int(bitrate_part.split("k.")[0])

            # Initialize resolution entry if not exists
            if resolution_part not in curves:
                curves[resolution_part] = {}

            # Add bitrate->quality mapping
            quality = metric.vmaf if use_vmaf else metric.psnr
            curves[resolution_part][bitrate] = quality

        except (IndexError, ValueError) as e:
            logger.warning(f"Error parsing encoding_id '{metric.encoding_id}': {str(e)}")
            continue

    return curves


def _determine_complexity_category(
    content_analysis, quality_metrics: List[QualityMetric]
) -> Tuple[ComplexityCategory, float]:
    """
    Determine the complexity category based on content analysis and quality metrics.

    Args:
        content_analysis: Content analysis results
        quality_metrics: List of quality metrics

    Returns:
        Tuple of (complexity_category, weighted_score)
    """
    # Extract scores from content analysis
    motion = content_analysis.motion_intensity.score
    temporal = content_analysis.temporal_complexity.score
    spatial = content_analysis.spatial_complexity.score
    scene_changes = content_analysis.scene_change_frequency.score
    texture = content_analysis.texture_detail_prevalence.score

    # Calculate weighted average based on specification
    weights = {"motion": 0.35, "temporal": 0.25, "spatial": 0.20, "scene_changes": 0.10, "texture": 0.10}

    weighted_score = (
        motion * weights["motion"]
        + temporal * weights["temporal"]
        + spatial * weights["spatial"]
        + scene_changes * weights["scene_changes"]
        + texture * weights["texture"]
    )

    # Apply quality metrics analysis as an adjustment factor
    # Check how much quality is lost at lower bitrates

    # Get bitrate-quality curves
    curves = _calculate_bitrate_quality_curve(quality_metrics, use_vmaf=True)

    # Calculate quality loss factor if we have enough data
    quality_loss_factor = 0
    if curves:
        # For each resolution, calculate quality loss from highest to lowest bitrate
        quality_loss_values = []

        for resolution, bitrate_quality in curves.items():
            if len(bitrate_quality) >= 2:  # Need at least 2 points to calculate loss
                bitrates = sorted(bitrate_quality.keys())
                max_quality = bitrate_quality[bitrates[-1]]  # Highest bitrate quality
                min_quality = bitrate_quality[bitrates[0]]  # Lowest bitrate quality

                # Calculate percentage quality loss
                if max_quality > 0:
                    quality_loss = (max_quality - min_quality) / max_quality * 100
                    quality_loss_values.append(quality_loss)

        # Average quality loss across all resolutions
        if quality_loss_values:
            quality_loss_factor = sum(quality_loss_values) / len(quality_loss_values)

            # Adjust weighted score based on quality loss factor
            # More quality loss indicates more complex content
            weighted_score = weighted_score * (1 + quality_loss_factor / 200)

    # Cap the weighted score at 100
    weighted_score = min(weighted_score, 100)

    # Determine complexity category based on weighted score
    if weighted_score < 40:
        category = ComplexityCategory.LOW
    elif weighted_score < 60:
        category = ComplexityCategory.MEDIUM
    elif weighted_score < 80:
        category = ComplexityCategory.HIGH
    else:
        category = ComplexityCategory.ULTRA_HIGH

    return category, weighted_score


def aggregate_data(state: EnCodexState) -> EnCodexState:
    """
    Aggregates content analysis and quality metrics data.

    Args:
        state: Current workflow state

    Returns:
        Updated workflow state with aggregated data
    """
    if not state.content_analysis or not state.quality_metrics:
        state.error = "Missing content analysis or quality metrics data"
        logger.error(state.error)
        return state

    logger.info("Starting data aggregation node.")

    # Extract content characteristics from content analysis
    logger.info("Analyzing content characteristics...")
    logger.info(f"Motion intensity: {state.content_analysis.motion_intensity.score:.1f}")
    logger.info(f"Temporal complexity: {state.content_analysis.temporal_complexity.score:.1f}")
    logger.info(f"Spatial complexity: {state.content_analysis.spatial_complexity.score:.1f}")
    logger.info(f"Scene change frequency: {state.content_analysis.scene_change_frequency.score:.1f}")
    logger.info(f"Texture detail: {state.content_analysis.texture_detail_prevalence.score:.1f}")
    logger.info(f"Animation type: {state.content_analysis.animation_type.type}")

    # Analyze quality metrics
    logger.info(f"Analyzing quality metrics for {len(state.quality_metrics)} test encodings...")

    # Calculate bitrate vs. quality curves
    vmaf_curves = _calculate_bitrate_quality_curve(state.quality_metrics, use_vmaf=True)
    _calculate_bitrate_quality_curve(state.quality_metrics, use_vmaf=False)

    # Log some summary statistics
    for resolution, bitrate_quality in vmaf_curves.items():
        bitrates = sorted(bitrate_quality.keys())
        if bitrates:
            min_bitrate = bitrates[0]
            # max_bitrate = bitrates[-1]
            min_vmaf = bitrate_quality[min_bitrate]
            # max_vmaf = bitrate_quality[max_bitrate]
            logger.info(
                (
                    f"Resolution {resolution}: VMAF range {min_vmaf:.1f} "
                    "@ {min_bitrate}k to {max_vmaf:.1f} @ {max_bitrate}k"
                )
            )

    # Determine complexity category
    category, score = _determine_complexity_category(state.content_analysis, state.quality_metrics)
    state.complexity_category = category

    logger.info(f"Determined complexity category: {category.value} (score: {score:.1f})")
    logger.info("Finished data aggregation node.")

    return state
