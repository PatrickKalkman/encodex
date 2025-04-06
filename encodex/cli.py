import argparse
import os
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


def analyze_video(video_path: str) -> None:
    """
    Analyzes a video file using the Google Generative AI API.

    Args:
        video_path: The path to the video file.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(video_path):
        print(f"Error: Video file not found at {video_path}", file=sys.stderr)
        sys.exit(1)

    try:
        client = genai.Client(api_key=api_key)

        print(f"Uploading file: {video_path}...")
        # Set a longer timeout (e.g., 600 seconds = 10 minutes)
        request_options = {"timeout": 600}
        # TODO: Add more specific error handling for file upload
        # request_options is not valid for files.upload
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
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json"  # Request JSON output
            ),
            request_options=request_options,  # Apply the same timeout here
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


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Analyze video content characteristics using Generative AI.")
    parser.add_argument("video_path", help="Path to the video file to analyze.")
    args = parser.parse_args()

    analyze_video(args.video_path)


if __name__ == "__main__":
    main()
