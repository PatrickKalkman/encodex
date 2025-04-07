"""
LangGraph setup for the EncodEx workflow.
"""

from langgraph.graph import StateGraph

from encodex.graph_state import EncodExState
from encodex.nodes.content_analyzer import analyze_content
from encodex.nodes.input_processor import process_input
from encodex.nodes.low_res_encoder import create_low_res_preview
from encodex.nodes.placeholder_nodes import (
    aggregate_data,
    calculate_quality_metrics,
    generate_output,
    generate_recommendations,
    generate_test_encodings,
)

# from encodex.nodes.segment_selector import select_segments # Removed
from encodex.nodes.video_splitter import split_video


def create_graph():
    """Create the EncodEx workflow graph."""
    # Define the graph with the EncodExState as the state type
    workflow = StateGraph(EncodExState)

    # Add all nodes to the graph
    workflow.add_node("input_processor", process_input)
    workflow.add_node("low_res_encoder", create_low_res_preview)
    workflow.add_node("video_splitter", split_video)
    workflow.add_node("content_analyzer", analyze_content)
    # workflow.add_node("segment_selector", select_segments) # Removed
    workflow.add_node("test_encoding_generator", generate_test_encodings)
    workflow.add_node("quality_metrics_calculator", calculate_quality_metrics)
    workflow.add_node("data_aggregator", aggregate_data)
    workflow.add_node("recommendation_engine", generate_recommendations)
    workflow.add_node("output_generator", generate_output)

    # Connect the nodes in a linear flow
    workflow.add_edge("input_processor", "low_res_encoder")
    workflow.add_edge("low_res_encoder", "video_splitter")
    workflow.add_edge("video_splitter", "content_analyzer")
    # workflow.add_edge("content_analyzer", "segment_selector") # Removed
    workflow.add_edge("content_analyzer", "test_encoding_generator") # Changed source
    workflow.add_edge("test_encoding_generator", "quality_metrics_calculator")
    workflow.add_edge("quality_metrics_calculator", "data_aggregator")
    workflow.add_edge("data_aggregator", "recommendation_engine")
    workflow.add_edge("recommendation_engine", "output_generator")

    # Define entry point
    workflow.set_entry_point("input_processor")

    # Compile the graph
    return workflow.compile()


def get_node_function(node_name: str):
    """Get a specific node function for testing."""
    node_map = {
        "input_processor": process_input,
        "low_res_encoder": create_low_res_preview,
        "video_splitter": split_video,
        "content_analyzer": analyze_content,
        # "segment_selector": select_segments, # Removed
        "test_encoding_generator": generate_test_encodings,
        "quality_metrics_calculator": calculate_quality_metrics,
        "data_aggregator": aggregate_data,
        "recommendation_engine": generate_recommendations,
        "output_generator": generate_output,
    }

    return node_map.get(node_name)
