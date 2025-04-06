import argparse
import os

# Import requests exceptions if you suspect lower-level HTTP issues
# import requests.exceptions
import re  # Add import for regex
import sys
import time

from google import genai

ANALYSIS_PROMPT = """
Analyze this video sample and provide a structured assessment of the following
content characteristics that impact video compression efficiency. For each
numerical characteristic, provide a score from 0-100 and a brief justification:

1. Motion intensity: [Score] - [Justification]
2. Temporal complexity: [Score] - [Justification]
3. Spatial complexity: [Score] - [Justification]
4. Scene change frequency: [Score] - [Justification]
5. Texture detail prevalence: [Score] - [Justification]
6. Contrast levels: [Score] - [Justification]
7. Animation type: [Type] - [Justification]
8. Grain/noise levels: [Score] - [Justification]

Also identify 3-5 representative segments (with timestamp ranges) that would be
useful for encoding tests, including high-complexity, medium-complexity, and
low-complexity sections.

Provide the output in JSON format.
"""

# Regex to check if the input looks like a Gemini File API URI (e.g., "files/...")
GEMINI_FILE_URI_PATTERN = r"^files\/[a-zA-Z0-9_-]+$"


def analyze_video(input_source: str) -> None:
    """
    Analyzes a video using the Google Generative AI API, accepting either a
    local file path or a Gemini File API URI (e.g., "files/xyz123").

    Args:
        input_source: The path to the local video file or the URI of a
                      previously uploaded file.
    """
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

            except Exception as e:  # Catch specific errors? e.g. NotFound
                print(f"Error retrieving file URI {input_source}: {e}", file=sys.stderr)
                sys.exit(1)

        elif os.path.exists(input_source):
            print(f"Uploading local file: {input_source}...")
            # TODO: Add more specific error handling for file upload
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
            if video_file.state.name == "FAILED" and hasattr(video_file, "error") and video_file.error:
                print(f"Reason: {video_file.error.message}", file=sys.stderr)
            # Optionally delete the failed upload/file?
            # client.files.delete(name=video_file.name)
            sys.exit(1)

        print("Video file is active and ready for analysis.")
        # --- Content Generation ---
        # model = "gemini-1.5-pro-latest"  # Using a more stable model as default
        model = "gemini-2.5-pro-preview-03-25" # Keep if you specifically need this preview
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

            # Optional: Delete the file only if it was uploaded in this run?
            # if not re.match(GEMINI_FILE_URI_PATTERN, input_source):
            #     print(f"\nDeleting uploaded file: {video_file.name}")
            #     client.files.delete(name=video_file.name)

        except Exception as gen_e:
            print(f"\nError during content generation: {gen_e}", file=sys.stderr)
            # Suggest reusing the file if generation failed but file is active
            if video_file and video_file.state.name == "ACTIVE":
                print(f"\nThe video file '{video_file.name}' is processed and active.", file=sys.stderr)
                print("You can try analyzing it again later using its URI:", file=sys.stderr)
                print(f"  python -m encodex.cli {video_file.name}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        # Catch-all for other potential errors (e.g., client init)
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


def _initialize_genai_client() -> genai.Client:
    """Initializes and returns the Google Generative AI client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    # http_options = HttpOptions(timeout=180.0) # Removed as per user feedback
    return genai.Client(api_key=api_key)


def list_uploaded_files() -> None:
    """Lists files previously uploaded via the File API."""
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


def delete_all_files() -> None:
    """Deletes all files previously uploaded via the File API."""
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


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Analyze video content using Generative AI, list, or delete uploaded files.",
        formatter_class=argparse.RawTextHelpFormatter,  # Keep formatting in help
    )
    parser.add_argument(
        "input_source",
        nargs="?",
        default=None,
        help="Path to the local video file to analyze OR\n"
        "the URI of a previously uploaded file (e.g., 'files/xyz123').\n"
        "Required unless using --list-files or --delete-all-files.",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List all files previously uploaded via the File API.",
    )
    parser.add_argument(
        "--delete-all-files",
        action="store_true",
        help="Delete all files previously uploaded via the File API.",
    )
    args = parser.parse_args()

    # Ensure mutual exclusivity
    action_count = sum([args.list_files, args.delete_all_files, bool(args.input_source)])
    if action_count > 1:
        parser.print_help()
        print(
            "\nError: Only one action (analyze video/URI, --list-files, or --delete-all-files) can be specified at a time.",
            file=sys.stderr,
        )
        sys.exit(1)
    elif action_count == 0:
        parser.print_help()
        print(
            "\nError: You must specify an action (input_source, --list-files, or --delete-all-files).", file=sys.stderr
        )
        sys.exit(1)

    if args.list_files:
        list_uploaded_files()
    elif args.delete_all_files:
        # TODO: Add a confirmation step before deleting?
        delete_all_files()
    elif args.input_source:
        analyze_video(args.input_source)
    # The 'else' case for no action is handled by the check above


if __name__ == "__main__":
    main()
