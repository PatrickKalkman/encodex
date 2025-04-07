"""
Content analyzer node for analyzing video content using Google Gemini.
"""

import json
import os
import re
import time
from typing import Any, Dict, Optional

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


def _get_or_upload_video(client: genai.Client, video_path: str, existing_uri: Optional[str]) -> Optional[Any]:
    """
    Get video file from Gemini using URI if available and ACTIVE, otherwise upload.

    Args:
        client: Initialized Gemini client.
        video_path: Local path to the video file.
        existing_uri: Existing Gemini File API URI, if known.

    Returns:
        The Gemini file object if ACTIVE, otherwise None.
    """
    video_file = None

    # 1. Try using the existing URI if provided
    if existing_uri:
        print(f"Attempting to retrieve existing file using URI: {existing_uri}")
        try:
            video_file = client.files.get(name=existing_uri)
            print(f"Retrieved file: {video_file.name} (State: {video_file.state.name})")
            # If retrieved, check its state and wait if necessary
            while video_file.state.name == "PROCESSING":
                print(f"File {video_file.name} is still processing, waiting...")
                time.sleep(5)
                video_file = client.files.get(name=video_file.name)
                print(f"File state: {video_file.state.name}")

            if video_file.state.name == "ACTIVE":
                print(f"Using existing ACTIVE file: {video_file.name}")
                return video_file
            else:
                print(
                    f"Existing file {video_file.name} is not ACTIVE "
                    f"(State: {video_file.state.name}). Will re-upload."
                )
                video_file = None # Reset video_file to trigger upload

        except Exception as e:
            print(f"Failed to retrieve or process existing file URI {existing_uri}: {e}. Will attempt upload.")
            video_file = None # Reset video_file to trigger upload

    # 2. Upload if no valid existing file found
    if video_file is None:
        if not os.path.exists(video_path):
             print(f"Error: Local video file not found for upload: {video_path}")
             return None # Cannot upload if local file is missing

        print(f"Uploading {video_path} to Gemini API...")
        try:
            video_file = client.files.upload(file=video_path)
            print(f"Uploaded file: {video_file.name} (State: {video_file.state.name})")
        except Exception as e:
            print(f"Error uploading file {video_path}: {e}")
            return None # Upload failed

        # Wait for the video to be processed after upload
        while video_file.state.name == "PROCESSING":
            print(f"Processing uploaded video {video_file.name}...")
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)
            print(f"File state: {video_file.state.name}")

    # 3. Final check on state after retrieval or upload attempt
    if video_file and video_file.state.name == "ACTIVE":
        print(f"File {video_file.name} is ACTIVE.")
        return video_file
    elif video_file:
        print(f"Error: File {video_file.name} ended in non-ACTIVE state: {video_file.state.name}")
        # Optionally try to delete the failed file?
        # try:
        #     print(f"Attempting to delete non-ACTIVE file {video_file.name}...")
        #     client.files.delete(name=video_file.name)
        #     print("Deleted.")
        # except Exception as del_e:
        #     print(f"Could not delete non-ACTIVE file {video_file.name}: {del_e}")
        return None
    else:
        # This case happens if upload failed or local file was missing
        print(f"Could not obtain an ACTIVE video file for {video_path}.")
        return None


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
    print("Starting content analysis node...")
    # Validate input
    if not state.chunk_paths:
        print("Error: Missing video chunk paths in state.")
        state.error = "Missing video chunk paths"
        return state

    # Initialize chunk_uri_map if it's None
    if state.chunk_uri_map is None:
        state.chunk_uri_map = {}

    try:
        print("Initializing Gemini client...")
        client = _initialize_genai_client()
        print("Gemini client initialized.")

        # Select chunks for analysis: first, middle, last (or fewer if not enough chunks)
        num_chunks = len(state.chunk_paths)
        selected_chunk_indices = set()
        if num_chunks > 0:
            selected_chunk_indices.add(0)  # First chunk
        if num_chunks > 2:
            selected_chunk_indices.add(num_chunks // 2) # Middle chunk
        if num_chunks > 1:
            selected_chunk_indices.add(num_chunks - 1) # Last chunk

        chunks_to_analyze = [state.chunk_paths[i] for i in sorted(list(selected_chunk_indices))]
        print(f"Selected chunks for analysis: {chunks_to_analyze}")

        # Process selected chunks
        all_results = []
        for chunk_path in chunks_to_analyze:
            print(f"--- Processing video chunk: {chunk_path} ---")

            # Get existing URI or None
            existing_uri = state.chunk_uri_map.get(chunk_path)

            # Try to get existing file or upload new one
            video_file = _get_or_upload_video(client, chunk_path, existing_uri)

            if not video_file:
                # Error handled within _get_or_upload_video, skip analysis for this chunk
                print(f"Skipping analysis for chunk {chunk_path} due to file processing error.")
                # Optionally set a partial error state?
                # state.error = f"Failed to process chunk {chunk_path}" # This might halt workflow
                continue # Move to the next chunk

            # Store the URI in the state map if it's not already there or if it was just uploaded
            if chunk_path not in state.chunk_uri_map or state.chunk_uri_map[chunk_path] != video_file.uri:
                 print(f"Updating state map: {chunk_path} -> {video_file.uri}")
                 state.chunk_uri_map[chunk_path] = video_file.uri

            # Analyze with Gemini using the ACTIVE file
            print(f"Requesting analysis from Gemini for {video_file.uri}...")
            try:
                analysis_text = _analyze_with_gemini(client, video_file)
                print("Received analysis response from Gemini.")
                # print(f"Raw analysis text:\n{analysis_text}") # Optional: Log raw response
            except Exception as analysis_e:
                 print(f"Error during Gemini analysis for {video_file.uri}: {analysis_e}")
                 # Decide how to handle: skip chunk, set error, etc.
                 # For now, let's skip this chunk's result but continue with others
                 continue

            # Parse the response
            print("Parsing analysis response...")
            analysis_data = _parse_analysis_result(analysis_text)
            print("Analysis response parsed successfully.")
            # print(f"Parsed analysis data: {analysis_data}") # Optional: Log parsed data
            all_results.append(analysis_data)

            # Optionally delete the file from Gemini
            # Note: We are NOT deleting the file from Gemini anymore,
            # as we want to reuse the URI later.
            print(f"--- Finished processing chunk: {chunk_path} ---")

        # Combine results (using first *successful* result for now)
        print("Combining analysis results...")
        if all_results:
            # TODO: Implement a more sophisticated result combination strategy
            # For now, just use the first successful analysis we got.
            print("Using analysis result from the first successfully analyzed chunk.")
            result = all_results[0] # Assumes at least one chunk succeeded

            # Map to ContentAnalysis model
            print("Mapping raw analysis data to ContentAnalysis model...")
            content_analysis = _map_to_content_analysis(result)
            print("Mapping successful.")

            # Update state
            print("Updating state with content analysis...")
            state.content_analysis = content_analysis
            print("State updated.")

        else:
            print("Error: No analysis results were obtained from Gemini.")
            state.error = "No analysis results returned from Gemini"

        print("Content analysis node finished successfully.")
        return state

    except Exception as e:
        print(f"Error during content analysis: {str(e)}")
        state.error = f"Error analyzing content: {str(e)}"
        print("Content analysis node finished with error.")
        return state
