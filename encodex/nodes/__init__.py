"""
Node implementations for the EncodEx LangGraph workflow.
"""

__version__ = "0.1.0"

# Import node functions to make them available at the package level
from encodex.nodes.content_analyzer import analyze_content
from encodex.nodes.input_processor import process_input
from encodex.nodes.low_res_encoder import create_low_res_preview

# Placeholder imports for future nodes (commented out)
# from encodex.nodes.segment_selector import select_segments
# from encodex.nodes.test_encoding_generator import generate_test_encodings
# from encodex.nodes.quality_metrics_calculator import calculate_quality_metrics
# from encodex.nodes.data_aggregator import aggregate_data
# from encodex.nodes.recommendation_engine import generate_recommendations
# from encodex.nodes.output_generator import generate_output

# Define the public API of the nodes package
__all__ = [
    "analyze_content",
    "process_input",
    "create_low_res_preview",
    # Add future node function names here as they are implemented
    # "select_segments",
    # "generate_test_encodings",
    # "calculate_quality_metrics",
    # "aggregate_data",
    # "generate_recommendations",
    # "generate_output",
]
