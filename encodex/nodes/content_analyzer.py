"""
Content analyzer node for analyzing video content using Google Gemini.
"""

import json
import os
import re
import time
from typing import Any, Dict

from google import genai

from encodex.graph_state import AnimationType, ContentAnalysis, ContentCharacteristic, EncodExState

# Regex to check if the input looks like a Gemini File API URI (e.g., "files/...")
GEMINI_FILE_URI_PATTERN = r"^files\/[a-zA-Z0-9_-]+$"

# Analysis prompt from the spec
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


def _initialize_genai_client() -> genai.Client:
    """Initialize the Google Generative AI client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    return genai.Client(api_key=api_key)


def _upload_video_to_gemini(client: genai.Client, video_path: str) -> Any:
    """Upload a video file to Gemini API."""
    print(f"Uploading {video_path} to Gemini API...")
    video_file = client.files.upload(file=video_path)

    # Wait for the video to be processed
    while video_file.state.name == "PROCESSING":
        print("Processing video...")
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name != "ACTIVE":
        raise ValueError(f"Video file processing failed: {video_file.state.name}")

    return video_file


def _analyze_with_gemini(client: genai.Client, video_file: Any) -> str:
    """Use Gemini API to analyze the video content."""
    model = "gemini-2.5-pro-preview-03-25"  # Using a specific model as in cli.py
    print(f"Generating analysis using model: {model}...")

    response = client.models.generate_content(
        model=model,
        contents=[
            video_file,
            ANALYSIS_PROMPT,
        ],
    )

    return response.text


def _parse_analysis_result(json_str: str) -> Dict[str, Any]:
    """Parse JSON response from Gemini API."""
    # Extract JSON from markdown code blocks if present
    json_match = re.search(r"```json\s*(.*?)\s*```", json_str, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON response: {e}")


def _map_to_content_analysis(analysis_data: Dict[str, Any]) -> ContentAnalysis:
    """Map raw analysis data to ContentAnalysis model."""
    video_assessment = analysis_data.get("video_assessment", {})

    return ContentAnalysis(
        motion_intensity=ContentCharacteristic(
            score=float(video_assessment.get("motion_intensity", {}).get("score", 0)),
            justification=video_assessment.get("motion_intensity", {}).get("justification", ""),
        ),
        temporal_complexity=ContentCharacteristic(
            score=float(video_assessment.get("temporal_complexity", {}).get("score", 0)),
            justification=video_assessment.get("temporal_complexity", {}).get("justification", ""),
        ),
        spatial_complexity=ContentCharacteristic(
            score=float(video_assessment.get("spatial_complexity", {}).get("score", 0)),
            justification=video_assessment.get("spatial_complexity", {}).get("justification", ""),
        ),
        scene_change_frequency=ContentCharacteristic(
            score=float(video_assessment.get("scene_change_frequency", {}).get("score", 0)),
            justification=video_assessment.get("scene_change_frequency", {}).get("justification", ""),
        ),
        texture_detail_prevalence=ContentCharacteristic(
            score=float(video_assessment.get("texture_detail_prevalence", {}).get("score", 0)),
            justification=video_assessment.get("texture_detail_prevalence", {}).get("justification", ""),
        ),
        contrast_levels=ContentCharacteristic(
            score=float(video_assessment.get("contrast_levels", {}).get("score", 0)),
            justification=video_assessment.get("contrast_levels", {}).get("justification", ""),
        ),
        animation_type=AnimationType(
            type=video_assessment.get("animation_type", {}).get("type", "Unknown"),
            justification=video_assessment.get("animation_type", {}).get("justification", ""),
        ),
        grain_noise_levels=ContentCharacteristic(
            score=float(video_assessment.get("grain_noise_levels", {}).get("score", 0)),
            justification=video_assessment.get("grain_noise_levels", {}).get("justification", ""),
        ),
    )


def analyze_content(state: EncodExState) -> EncodExState:
    """
    Analyze video content using Google Gemini API.

    Args:
        state: Current graph state with chunk_paths from video_splitter

    Returns:
        Updated state with content_analysis
    """
    # Validate input
    if not state.chunk_paths:
        state.error = "Missing video chunk paths"
        return state

    try:
        # Initialize Gemini client
        client = _initialize_genai_client()

        # Process each chunk
        all_results = []

        for chunk_path in state.chunk_paths:
            print(f"Processing video chunk: {chunk_path}")

            # Upload to Gemini
            video_file = _upload_video_to_gemini(client, chunk_path)

            # Analyze with Gemini
            analysis_text = _analyze_with_gemini(client, video_file)

            # Parse the response
            analysis_data = _parse_analysis_result(analysis_text)
            all_results.append(analysis_data)

            # Optionally delete the file from Gemini
            # client.files.delete(name=video_file.name)

        # Combine results (using first result for now, will be enhanced later)
        if all_results:
            result = all_results[0]

            # Map to ContentAnalysis model
            content_analysis = _map_to_content_analysis(result)

            # Update state
            state.content_analysis = content_analysis

        else:
            state.error = "No analysis results returned from Gemini"

        return state

    except Exception as e:
        state.error = f"Error analyzing content: {str(e)}"
        return state
