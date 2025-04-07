"""
Command-line interface for the EncodEx system.
"""

import argparse
import os
import sys
import time

from encodex.graph import create_graph
from encodex.graph_state import EncodExState
from encodex.node_runner import load_state_from_json, run_node, save_state_to_json


def run_single_node(args):
    """
    Run a single node of the EncodEx workflow.

    Args:
        args: Command line arguments
    """
    node_name = args.node
    input_file = args.input
    input_state_path = args.state
    output_path = args.output

    try:
        # Load input state if provided
        input_state = None
        if input_state_path:
            input_state = load_state_from_json(input_state_path)

        # Run the node
        updated_state = run_node(node_name, input_state, input_file)

        # Print error if present
        if updated_state.error:
            print(f"Error: {updated_state.error}", file=sys.stderr)
            sys.exit(1)

        # Save output state if requested
        if output_path:
            save_state_to_json(updated_state, output_path)
            print(f"Saved state to {output_path}")

        # Print summary of updated state
        print("\nNode execution completed successfully.")
        print(f"Node: {node_name}")

        if node_name == "input_processor" and updated_state.video_metadata:
            meta = updated_state.video_metadata
            print("\nVideo Metadata:")
            print(f"  Duration: {meta.duration:.2f} seconds")
            print(f"  Resolution: {meta.width}x{meta.height}")
            print(f"  FPS: {meta.fps}")
            print(f"  Codec: {meta.codec}")
            print(f"  Bitrate: {meta.bitrate} bps")

        elif node_name == "low_res_encoder" and updated_state.low_res_path:
            print(f"\nLow-res preview created: {updated_state.low_res_path}")

        elif node_name == "content_analyzer" and updated_state.content_analysis:
            analysis = updated_state.content_analysis
            print("\nContent Analysis:")
            print(f"  Motion Intensity: {analysis.motion_intensity.score:.1f}")
            print(f"  Temporal Complexity: {analysis.temporal_complexity.score:.1f}")
            print(f"  Spatial Complexity: {analysis.spatial_complexity.score:.1f}")
            print(f"  Animation Type: {analysis.animation_type.type}")

    except Exception as e:
        print(f"Error running node {node_name}: {str(e)}", file=sys.stderr)
        sys.exit(1)


def run_full_workflow(args):
    """
    Run the complete EncodEx workflow.

    Args:
        args: Command line arguments
    """
    input_file = args.input
    output_path = args.output

    try:
        # Create initial state
        initial_state = EncodExState(input_file=input_file)

        # Create and run the workflow
        workflow = create_graph()
        final_state = workflow.invoke({"state": initial_state})

        # Check for errors
        if final_state.error:
            print(f"Error: {final_state.error}", file=sys.stderr)
            sys.exit(1)

        # Save output if requested
        if output_path:
            save_state_to_json(final_state, output_path)
            print(f"Saved output to {output_path}")

        # Print summary
        print("\nWorkflow completed successfully.")
        if final_state.encoding_ladder:
            print("\nRecommended Encoding Ladder:")
            for level in final_state.encoding_ladder:
                print(f"  {level.resolution}: {level.bitrate} ({level.profile})")

        if final_state.estimated_savings:
            print(f"\nEstimated savings: {final_state.estimated_savings}")

    except Exception as e:
        print(f"Error running workflow: {str(e)}", file=sys.stderr)
        sys.exit(1)


def list_uploaded_files():
    """
    List files uploaded to Gemini API.
    This function is kept for backward compatibility with the original CLI.
    """
    # Import here to avoid circular imports
    from encodex.nodes.content_analyzer import _initialize_genai_client

    try:
        client = _initialize_genai_client()
        print("Listing uploaded files:")
        count = 0
        for f in client.files.list():
            print(f"  - Name: {f.name}")
            print(f"    URI: {f.uri}")
            print(f"    State: {f.state.name}")
            print(f"    Expiration: {f.expiration_time}")
            print("-" * 20)
            count += 1
        if count == 0:
            print("  No files found.")
    except Exception as e:
        print(f"An error occurred while listing files: {e}", file=sys.stderr)
        sys.exit(1)


def delete_all_files():
    """
    Delete all files uploaded to Gemini API.
    This function is kept for backward compatibility with the original CLI.
    """
    # Import here to avoid circular imports
    from encodex.nodes.content_analyzer import _initialize_genai_client

    try:
        client = _initialize_genai_client()
        print("Attempting to delete all uploaded files...")
        deleted_count = 0
        failed_count = 0
        files_to_delete = list(client.files.list())  # Get the list first

        if not files_to_delete:
            print("No files found to delete.")
            return

        for f in files_to_delete:
            try:
                print(f"  Deleting file: {f.name} (URI: {f.uri})...", end="")
                client.files.delete(name=f.name)
                print(" Done.")
                deleted_count += 1
            except Exception as delete_error:
                print(f" Failed. Error: {delete_error}")
                failed_count += 1

        print("-" * 20)
        print(f"Deletion summary: {deleted_count} deleted, {failed_count} failed.")

    except Exception as e:
        print(f"An error occurred during the deletion process: {e}", file=sys.stderr)
        sys.exit(1)


def analyze_video_directly(input_source):
    """
    Direct video analysis using Gemini API - kept for backward compatibility.

    Args:
        input_source: Path to video file or Gemini file URI
    """
    # Import here to avoid circular imports
    import re

    from encodex.nodes.content_analyzer import ANALYSIS_PROMPT, GEMINI_FILE_URI_PATTERN, _initialize_genai_client

    client = _initialize_genai_client()
    video_file = None

    try:
        # Check if input_source is a URI or a local path
        if re.match(GEMINI_FILE_URI_PATTERN, input_source):
            print(f"Using existing file URI: {input_source}")
            try:
                video_file = client.files.get(name=input_source)
                print(f"Found file: {video_file.name} (State: {video_file.state.name})")
                # No need to wait for processing if it's already ACTIVE
                if video_file.state.name == "PROCESSING":
                    print("File is still processing, please wait and try again later or wait here.")
                    # Optional: Add waiting loop here if desired, similar to upload
                    while video_file.state.name == "PROCESSING":
                        time.sleep(5)
                        video_file = client.files.get(name=video_file.name)
                        print(f"File state: {video_file.state.name}")

            except Exception as e:
                print(f"Error retrieving file URI {input_source}: {e}", file=sys.stderr)
                sys.exit(1)

        elif os.path.exists(input_source):
            print(f"Uploading local file: {input_source}...")
            video_file = client.files.upload(file=input_source)
            print(f"Uploaded file: {video_file.name} (State: {video_file.state.name})")

            # Wait for the video to be processed.
            while video_file.state.name == "PROCESSING":
                print("Processing video...")
                time.sleep(5)
                video_file = client.files.get(name=video_file.name)
                print(f"File state: {video_file.state.name}")
        else:
            print(f"Error: Input source not found or invalid: {input_source}", file=sys.stderr)
            print(
                "Please provide a valid local file path or a Gemini File API URI (e.g., 'files/xyz123').",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check final state after upload/retrieval
        if video_file.state.name != "ACTIVE":
            print(f"Error: Video file is not active. Final state: {video_file.state.name}", file=sys.stderr)
            if hasattr(video_file, "error") and video_file.error:
                print(f"Reason: {video_file.error.message}", file=sys.stderr)
            sys.exit(1)

        print("Video file is active and ready for analysis.")
        model = "gemini-2.5-pro-preview-03-25"  # Same as in content_analyzer.py
        print(f"Generating analysis using model: {model}...")

        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    video_file,  # Reference to the active video file object
                    ANALYSIS_PROMPT,
                ],
            )
            print("\nAnalysis Result:")
            print(response.text)

        except Exception as gen_e:
            print(f"\nError during content generation: {gen_e}", file=sys.stderr)
            if video_file and video_file.state.name == "ACTIVE":
                print(f"\nThe video file '{video_file.name}' is processed and active.", file=sys.stderr)
                print("You can try analyzing it again later using its URI:", file=sys.stderr)
                print(f"  python -m encodex.cli {video_file.name}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="EncodEx - AI-Driven Video Encoding Optimization System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Node runner command
    node_parser = subparsers.add_parser("node", help="Run a single node")
    node_parser.add_argument("node", help="Name of the node to run")
    node_parser.add_argument("--input", "-i", help="Path to input video file")
    node_parser.add_argument("--state", "-s", help="Path to input state JSON file")
    node_parser.add_argument("--output", "-o", help="Path to output state JSON file")

    # Workflow runner command
    workflow_parser = subparsers.add_parser("workflow", help="Run the complete workflow")
    workflow_parser.add_argument("--input", "-i", required=True, help="Path to input video file")
    workflow_parser.add_argument("--output", "-o", help="Path to output JSON file")

    # Legacy commands for backward compatibility
    legacy_parser = subparsers.add_parser("analyze", help="Analyze video with Gemini API directly")
    legacy_parser.add_argument("input", help="Path to video file or Gemini file URI")

    # list_parser = subparsers.add_parser("list-files", help="List files uploaded to Gemini API")
    # delete_parser = subparsers.add_parser("delete-files", help="Delete all files uploaded to Gemini API")

    # Parse arguments
    args = parser.parse_args()

    # Execute appropriate command
    if args.command == "node":
        if not args.input and not args.state:
            node_parser.error("Either --input or --state must be provided")
        run_single_node(args)

    elif args.command == "workflow":
        run_full_workflow(args)

    elif args.command == "analyze":
        analyze_video_directly(args.input)

    elif args.command == "list-files":
        list_uploaded_files()

    elif args.command == "delete-files":
        delete_all_files()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
