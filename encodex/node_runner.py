"""
Utility to run individual LangGraph nodes for testing.
"""

import json
import os
from typing import Optional

from encodex.graph import get_node_function
from encodex.graph_state import EncodExState


def run_node(
    node_name: str, input_state: Optional[EncodExState] = None, input_file: Optional[str] = None
) -> EncodExState:
    """
    Run a single node with a given state.

    Args:
        node_name: Name of the node to run
        input_state: Optional state to use as input
        input_file: Path to input video file (used if input_state is None)

    Returns:
        Updated state after node execution

    Raises:
        ValueError: If node doesn't exist or other validation errors
    """
    # Get the node function
    node_func = get_node_function(node_name)
    if not node_func:
        raise ValueError(f"Node not found: {node_name}")

    # Create initial state if not provided
    if not input_state:
        if not input_file:
            raise ValueError("Either input_state or input_file must be provided")

        if not os.path.exists(input_file):
            raise ValueError(f"Input file does not exist: {input_file}")

        # Create initial state with input file
        input_state = EncodExState(input_file=input_file)

    # Run the node
    updated_state = node_func(input_state)

    return updated_state


def load_state_from_json(json_path: str) -> EncodExState:
    """
    Load state from a JSON file.

    Args:
        json_path: Path to JSON file

    Returns:
        Loaded state
    """
    if not os.path.exists(json_path):
        raise ValueError(f"State file not found: {json_path}")

    with open(json_path, "r") as f:
        state_dict = json.load(f)

    return EncodExState.model_validate(state_dict)


def save_state_to_json(state: EncodExState, output_path: str) -> None:
    """
    Save state to a JSON file.

    Args:
        state: State to save
        output_path: Path to output JSON file
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Convert to dict and save
    state_dict = state.model_dump(exclude_none=True)

    with open(output_path, "w") as f:
        json.dump(state_dict, f, indent=2)
