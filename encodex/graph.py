"""
LangGraph setup for the EncodEx workflow.
"""

import functools

from langgraph.graph import StateGraph

from encodex.graph_state import EnCodexState
from encodex.nodes.content_analyzer import analyze_content
from encodex.nodes.data_aggregator import aggregate_data
from encodex.nodes.input_processor import process_input
from encodex.nodes.low_res_encoder import create_low_res_preview
from encodex.nodes.output_generator import generate_output
from encodex.nodes.quality_metrics_calculator import calculate_quality_metrics
from encodex.nodes.recommendation_engine import generate_recommendations
from encodex.nodes.test_encoding_generator import generate_test_encodings
from encodex.nodes.video_splitter import split_video


def create_graph(use_gpu: bool = False):
    """
    Create the EncodEx workflow graph.

    Args:
        use_gpu: Whether to attempt using GPU for relevant nodes.
    """
    # Define the graph with the EnCodexState as the state type
    workflow = StateGraph(EnCodexState)

    # Prepare node functions, potentially binding the use_gpu argument
    low_res_encoder_node = functools.partial(create_low_res_preview, use_gpu=use_gpu)
    test_encoding_generator_node = functools.partial(generate_test_encodings, use_gpu=use_gpu)

    # Add all nodes to the graph
    workflow.add_node("input_processor", process_input)
    workflow.add_node("low_res_encoder", low_res_encoder_node)
    workflow.add_node("video_splitter", split_video)
    workflow.add_node("content_analyzer", analyze_content)
    workflow.add_node("test_encoding_generator", test_encoding_generator_node)
    workflow.add_node("quality_metrics_calculator", calculate_quality_metrics)
    workflow.add_node("data_aggregator", aggregate_data)
    workflow.add_node("recommendation_engine", generate_recommendations)
    workflow.add_node("output_generator", generate_output)

    # Connect the nodes in a linear flow
    workflow.add_edge("input_processor", "low_res_encoder")
    workflow.add_edge("low_res_encoder", "video_splitter")
    workflow.add_edge("video_splitter", "content_analyzer")
    workflow.add_edge("content_analyzer", "test_encoding_generator")
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
        "test_encoding_generator": generate_test_encodings,
        "quality_metrics_calculator": calculate_quality_metrics,
        "data_aggregator": aggregate_data,
        "recommendation_engine": generate_recommendations,
        "output_generator": generate_output,
    }

    return node_map.get(node_name)
