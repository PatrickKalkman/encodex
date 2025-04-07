"""
Node implementations for the EncodEx LangGraph workflow.
"""

__version__ = "0.1.0"

# Import node functions to make them available at the package level
from encodex.nodes.content_analyzer import analyze_content
from encodex.nodes.input_processor import process_input
from encodex.nodes.low_res_encoder import create_low_res_preview
from encodex.nodes.test_encoding_generator import generate_test_encodings

# from encodex.nodes.segment_selector import select_segments # Removed
from encodex.nodes.video_splitter import split_video

"""
Node implementations for the EncodEx LangGraph workflow.
"""

# Import all node functions for easy access
# These will be implemented in future steps
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
    # "select_segments", # Removed
    "split_video",
    "generate_test_encodings",
    # "calculate_quality_metrics",
    # "aggregate_data",
    # "generate_recommendations",
    # "generate_output",
]
