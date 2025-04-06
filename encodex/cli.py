import argparse
import os
import sys
import time

from google import genai
from google.genai.types import HttpOptions

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


def analyze_video(video_path: str) -> None:
    """
    Analyzes a video file using the Google Generative AI API.

    Args:
        video_path: The path to the video file.
    """
    if not os.path.exists(video_path):
        print(f"Error: Video file not found at {video_path}", file=sys.stderr)
        sys.exit(1)

    try:
        client = _initialize_genai_client()

        print(f"Uploading file: {video_path}...")
        # TODO: Add more specific error handling for file upload
        uploaded_file = client.files.upload(file=video_path)
        print(f"Uploaded file: {uploaded_file.name} (State: {uploaded_file.state.name})")

        # Wait for the video to be processed.
        while uploaded_file.state.name == "PROCESSING":
            print("Processing video...")
            # Wait a few seconds before checking the status again.
            time.sleep(5)
            # Get the latest status of the file.
            uploaded_file = client.files.get(name=uploaded_file.name)
            print(f"File state: {uploaded_file.state.name}")

        if uploaded_file.state.name != "ACTIVE":
            print(f"Error: Video processing failed. Final state: {uploaded_file.state.name}", file=sys.stderr)
            # Optionally delete the failed upload
            # client.files.delete(name=uploaded_file.name)
            sys.exit(1)

        print("Video processing complete.")
        model = "gemini-2.5-pro-preview-03-25"
        print(f"Generating analysis using model: {model}...")

        # Generate content using the uploaded file and the prompt
        # TODO: Add error handling for content generation
        response = client.models.generate_content(
            model=model,
            contents=[
                uploaded_file,  # Reference to the uploaded video
                ANALYSIS_PROMPT,  # The analysis prompt
            ],
            # generation_config seems invalid here, rely on prompt for JSON format
        )

        # Process the response
        print("\nAnalysis Result:")
        print(response.text)

        # TODO: Consider deleting the uploaded file after analysis if needed
        # print(f"Deleting uploaded file: {uploaded_file.name}")
        # client.files.delete(name=uploaded_file.name)

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


def _initialize_genai_client() -> genai.Client:
    """Initializes and returns the Google Generative AI client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    # Set a timeout of 180 seconds (3 minutes)
    http_options = HttpOptions(timeout=180.0)
    return genai.Client(api_key=api_key, http_options=http_options)


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


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Analyze video content or list uploaded files using Generative AI.")
    parser.add_argument(
        "video_path",
        nargs="?",
        default=None,
        help="Path to the video file to analyze. Required unless --list-files is used.",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List all files previously uploaded via the File API.",
    )
    args = parser.parse_args()

    if args.list_files:
        if args.video_path:
            print("Warning: video_path argument ignored when --list-files is used.", file=sys.stderr)
        list_uploaded_files()
    elif args.video_path:
        analyze_video(args.video_path)
    else:
        parser.print_help()
        print("\nError: Either video_path or --list-files must be provided.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
