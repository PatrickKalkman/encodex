"""
Implementation of the recommendation engine node for the EncodEx workflow.

This node analyzes quality metrics using the convex hull approach to generate
optimal encoding parameters based on content complexity.
"""

import logging
from typing import Dict, List, Tuple

from encodex.graph_state import ComplexityCategory, EnCodexState, EncodingParameters, QualityMetric

# Set up logger
logger = logging.getLogger(__name__)


def _parse_encoding_id(encoding_id: str) -> Tuple[str, int]:
    """
    Parse the encoding ID to extract resolution and bitrate.

    Args:
        encoding_id: Format like "test_encoding_START-END_WIDTHxHEIGHT_BITRATEk.mp4"

    Returns:
        Tuple of (resolution, bitrate)
    """
    try:
        parts = encoding_id.split("_")
        resolution = parts[-2]  # e.g., "1280x720"
        bitrate_part = parts[-1]  # e.g., "4500k.mp4"
        bitrate = int(bitrate_part.split("k.")[0])
        return resolution, bitrate
    except (IndexError, ValueError) as e:
        logger.warning(f"Error parsing encoding_id '{encoding_id}': {str(e)}")
        return "unknown", 0


def _compute_convex_hull(quality_metrics: List[QualityMetric]) -> List[Dict]:
    """
    Compute the convex hull (Pareto frontier) of quality-bitrate points.

    Args:
        quality_metrics: List of quality metrics for test encodings

    Returns:
        List of points on the convex hull
    """
    logger.info("Computing convex hull from quality metrics...")

    # Parse encoding_id to extract resolution and bitrate
    parsed_metrics = []
    for metric in quality_metrics:
        resolution, bitrate = _parse_encoding_id(metric.encoding_id)
        parsed_metrics.append(
            {"encoding_id": metric.encoding_id, "resolution": resolution, "bitrate": bitrate, "vmaf": metric.vmaf}
        )

    # Sort by bitrate
    sorted_metrics = sorted(parsed_metrics, key=lambda x: x["bitrate"])

    # Compute convex hull (upper envelope)
    hull_points = []
    max_vmaf_so_far = -float("inf")

    for point in sorted_metrics:
        if point["vmaf"] > max_vmaf_so_far:
            hull_points.append(point)
            max_vmaf_so_far = point["vmaf"]

    logger.info(f"Found {len(hull_points)} points on the convex hull.")

    # Log the hull points
    for point in hull_points:
        logger.info(f"Hull point: {point['resolution']} @ {point['bitrate']}k -> VMAF {point['vmaf']:.2f}")

    return hull_points


def _refine_ladder_points(hull_points: List[Dict]) -> List[Dict]:
    """
    Refine ladder points to ensure reasonable spacing and a well-structured ladder.

    Args:
        hull_points: Points on the convex hull

    Returns:
        Refined list of ladder points
    """
    # Ensure hull points are sorted by bitrate (ascending)
    sorted_hull = sorted(hull_points, key=lambda x: x["bitrate"])

    # If we have very few points, return them all
    if len(sorted_hull) <= 4:
        return sorted_hull

    refined_points = []

    # Always include the lowest and highest bitrate points
    refined_points.append(sorted_hull[0])

    # Filter intermediate points to maintain reasonable spacing
    # Prefer keeping at least 1.5x bitrate jumps between ladder rungs
    last_added = sorted_hull[0]
    for point in sorted_hull[1:-1]:
        # Include the point if it's at least 1.5x the bitrate of the last added point
        # or if it's a resolution transition point (different resolution from the last)
        if point["bitrate"] >= last_added["bitrate"] * 1.5 or point["resolution"] != last_added["resolution"]:
            refined_points.append(point)
            last_added = point

    # Always include the highest bitrate point if not already added
    if sorted_hull[-1] != last_added:
        refined_points.append(sorted_hull[-1])

    logger.info(f"Refined ladder from {len(sorted_hull)} to {len(refined_points)} points.")
    return refined_points


def _get_adjustment_factor(complexity: ComplexityCategory) -> float:
    """
    Get bitrate adjustment factor based on content complexity.

    Args:
        complexity: Content complexity category

    Returns:
        Adjustment factor for bitrates
    """
    if complexity == ComplexityCategory.LOW:
        return 0.85  # Reduce bitrates by 15%
    elif complexity == ComplexityCategory.MEDIUM:
        return 1.0  # Use baseline bitrates
    elif complexity == ComplexityCategory.HIGH:
        return 1.15  # Increase bitrates by 15%
    elif complexity == ComplexityCategory.ULTRA_HIGH:
        return 1.3  # Increase bitrates by 30%
    else:
        return 1.0  # Default


def _select_profile(resolution: str) -> str:
    """
    Select H.264 profile based on resolution.

    Args:
        resolution: Resolution in the format "WIDTHxHEIGHT"

    Returns:
        Profile name (high, main, or baseline)
    """
    try:
        width, height = map(int, resolution.split("x"))

        if width >= 1280:  # HD and above
            return "high"
        elif width >= 640:  # SD
            return "main"
        else:  # Low resolutions
            return "baseline"
    except (ValueError, IndexError):
        # Default to main profile if resolution parsing fails
        return "main"


def _calculate_estimated_savings(encoding_ladder: List[EncodingParameters], complexity: ComplexityCategory) -> str:
    """
    Calculate estimated savings compared to baseline encoding ladder.

    Args:
        encoding_ladder: Recommended encoding ladder
        complexity: Content complexity category

    Returns:
        Estimated savings as a percentage string
    """
    # Baseline savings estimates based on complexity
    if complexity == ComplexityCategory.LOW:
        return "25%"  # Low complexity content can be compressed more efficiently
    elif complexity == ComplexityCategory.MEDIUM:
        return "15%"
    elif complexity == ComplexityCategory.HIGH:
        return "10%"
    elif complexity == ComplexityCategory.ULTRA_HIGH:
        return "5%"  # Ultra-high complexity content has less room for optimization
    else:
        return "15%"  # Default to moderate savings


def generate_recommendations(state: EnCodexState) -> EnCodexState:
    """
    Generates encoding parameter recommendations based on content analysis
    and quality metrics using convex hull optimization.

    Args:
        state: Current workflow state with quality metrics and complexity category

    Returns:
        Updated workflow state with encoding recommendations
    """
    if not state.quality_metrics:
        state.error = "Missing quality metrics for recommendation generation"
        logger.error(state.error)
        return state

    if not state.complexity_category:
        state.error = "Missing complexity category for recommendation generation"
        logger.error(state.error)
        return state

    logger.info("Starting recommendation engine node.")
    logger.info(f"Content complexity category: {state.complexity_category.value}")

    # Calculate convex hull from quality metrics
    hull_points = _compute_convex_hull(state.quality_metrics)

    # Refine ladder points for better spacing
    refined_points = _refine_ladder_points(hull_points)

    # Get bitrate adjustment factor based on complexity
    adjustment_factor = _get_adjustment_factor(state.complexity_category)
    logger.info(
        f"Using bitrate adjustment factor of {adjustment_factor:.2f} for {state.complexity_category.value} complexity"
    )

    # Generate encoding ladder
    encoding_ladder = []
    for point in refined_points:
        # Apply adjustment to bitrate based on content complexity
        adjusted_bitrate = int(point["bitrate"] * adjustment_factor)

        # Select profile based on resolution
        profile = _select_profile(point["resolution"])

        # Create encoding parameters
        encoding_params = EncodingParameters(
            resolution=point["resolution"], bitrate=f"{adjusted_bitrate}k", profile=profile
        )

        encoding_ladder.append(encoding_params)

    # Sort ladder by descending bitrate
    encoding_ladder.sort(key=lambda x: int(x.bitrate.rstrip("k")), reverse=True)

    # Calculate estimated savings
    estimated_savings = _calculate_estimated_savings(encoding_ladder, state.complexity_category)

    # Update state
    state.encoding_ladder = encoding_ladder
    state.estimated_savings = estimated_savings

    # Log the final encoding ladder
    logger.info("Generated encoding ladder:")
    for rung in encoding_ladder:
        logger.info(f"  {rung.resolution} @ {rung.bitrate} ({rung.profile})")
    logger.info(f"Estimated savings: {estimated_savings}")

    logger.info("Recommendation engine node finished.")
    return state
