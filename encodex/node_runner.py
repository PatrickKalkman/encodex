"""
Utility to run individual LangGraph nodes for testing.
"""

import inspect  # Import inspect module
import json
import os
from typing import Any, Dict, Optional

from encodex.graph import get_node_function
from encodex.graph_state import EncodExState


def run_node(
    node_name: str,
    input_state: Optional[EncodExState] = None,
    input_file: Optional[str] = None,
    **kwargs: Any # Accept arbitrary keyword arguments
) -> EncodExState:
    """
    Run a single node with a given state and optional node-specific arguments.

    Args:
        node_name: Name of the node to run
        input_state: Optional state to use as input
        input_file: Path to input video file (used if input_state is None)
        **kwargs: Additional keyword arguments to pass to the node function if accepted.

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
        current_state = EncodExState(input_file=input_file)
    else:
        current_state = input_state

    # Inspect the node function's signature
    sig = inspect.signature(node_func)
    node_params = sig.parameters

    # Prepare arguments for the node function call
    call_args: Dict[str, Any] = {}

    # Assume the first argument is always the state, or look for 'state' param
    first_param_name = next(iter(node_params))
    if 'state' in node_params:
         call_args['state'] = current_state
    elif node_params[first_param_name].annotation == EncodExState:
         call_args[first_param_name] = current_state
    else:
         # This case should ideally not happen if nodes follow the convention (state) -> state
         # Or if they type hint the state parameter correctly
         print(f"Warning: Node function {node_name} does not seem to accept 'state: EncodExState' argument correctly.")
         # Fallback: pass state as the first argument anyway
         call_args[first_param_name] = current_state


    # Add other arguments from kwargs if the function accepts them
    for key, value in kwargs.items():
        if key in node_params:
            # print(f"Passing argument '{key}={value}' to node '{node_name}'") # Optional: Log passed args
            call_args[key] = value
        else:
            # Don't warn by default, as many nodes won't accept extra args
            # print(f"Info: Argument '{key}' provided but not accepted by node '{node_name}'. Ignoring.")
            pass


    # Run the node with prepared arguments
    try:
        updated_state = node_func(**call_args)
        # Ensure the node returned a state object
        if not isinstance(updated_state, EncodExState):
             # If a node modifies state in-place and returns None, handle it
             if updated_state is None and 'state' in call_args:
                 print(f"Warning: Node '{node_name}' returned None. Assuming state was modified in-place.")
                 return call_args['state'] # Return the potentially modified input state
             else:
                 raise TypeError(f"Node '{node_name}' did not return an EncodExState object. Returned: {type(updated_state)}")
        return updated_state
    except Exception as e:
        # Optionally wrap the exception or add more context
        print(f"Error executing node '{node_name}': {e}")
        # Add error to the state before returning it
        current_state.error = f"Error executing node '{node_name}': {str(e)}"
        return current_state


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
    output_dir = os.path.dirname(output_path)
    if output_dir: # Ensure dirname is not empty (e.g., for relative paths in cwd)
        os.makedirs(output_dir, exist_ok=True)

    # Convert to dict and save
    # Use model_dump for Pydantic v2, exclude_none=True is default behavior
    # Use mode='json' to ensure types like Enums are serialized correctly
    state_dict = state.model_dump(mode='json', exclude_none=True)

    with open(output_path, "w") as f:
        # Use indent=2 for readability
        json.dump(state_dict, f, indent=2)
