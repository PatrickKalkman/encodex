"""
Content analyzer node for analyzing video content using Google Gemini.
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from google import genai

from encodex.graph_state import (  # Grouped imports
    AnimationType,
    ContentAnalysis,
    ContentCharacteristic,
    EncodExState,
    Segment,  # Added Segment
)

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

Use the following format:
{
  "assessment": {
    "motion_intensity": {
      "score": 75,
      "justification": "The video contains numerous high-action sequences including fights, explosions, magical \
effects, and fast camera movements (establishing shots, chases). While there are some static logo screens and \
dialogue scenes, the overall motion level is high."
    },
    "temporal_complexity": {
      "score": 80,
      "justification": "High temporal complexity due to frequent scene cuts, fast and often unpredictable motion \
(explosions, character powers, crowd movement), and significant use of particle effects and flashing lights \
(lightning, magic). Predicting subsequent frames is challenging."
    },
    "spatial_complexity": {
      "score": 85,
      "justification": "Very high spatial complexity. Scenes feature intricate details like ancient carvings, complex \
costumes, detailed rock textures, large crowds, detailed cityscapes (both ancient and modern), and elaborate CGI \
environments. Many frames are packed with visual information."
    },
    "scene_change_frequency": {
      "score": 85,
      "justification": "The video exhibits very frequent scene changes, typical of trailers and action sequences. \
Cuts occur rapidly, especially during the opening studio/DC logo montages and the action/historical segments."
    },
    "texture_detail_prevalence": {
      "score": 70,
      "justification": "Significant texture detail is prevalent, including rock faces, ancient stonework/carvings, \
clothing fabrics, dust, skin detail, and environmental textures. While some CGI elements might be smoother, \
detailed textures are common."
    },
    "contrast_levels": {
      "score": 80,
      "justification": "High contrast is present throughout. The video alternates between very dark scenes (logo \
sequences, cave interiors, night scenes) and scenes with extremely bright elements (sunlit landscapes, explosions, \
magical energy bursts)."
    },
    "animation_type": {
      "type": "Live Action / CGI Hybrid",
      "justification": "The video consists primarily of live-action footage heavily integrated with extensive \
computer-generated imagery (CGI) for visual effects, character abilities, environments, and large-scale destruction."
    },
    "grain_noise_levels": {
      "score": 40,
      "justification": "Moderate grain/noise. Some sequences, particularly the historical/ancient mining scenes \
(e.g., 1:45-2:30), appear to have intentional grain or stylization applied. Darker scenes may exhibit some minor \
digital noise, but it's not overly dominant across the entire sample."
    }
  },
  "representative_segments": [
    {
      "complexity": "Low",
      "timestamp_range": "0:15 - 0:21",
      "description": "New Line Cinema logo sequence. Relatively static logo with smooth background cloud animation."
    },
    {
      "complexity": "Medium",
      "timestamp_range": "10:53 - 11:08",
      "description": "Dialogue scene outside the van in the desert. Moderate character motion, clear textures on \
characters and van, relatively stable background, bright daylight."
    },
    {
      "complexity": "High",
      "timestamp_range": "1:45 - 1:59",
      "description": "Ancient mining scene. High spatial detail (rock textures, numerous people), significant motion \
(crowds mining), desaturated look potentially adding noise/grain complexity."
    },
    {
      "complexity": "High",
      "timestamp_range": "5:39 - 5:54",
      "description": "King puts on the crown, triggering a massive magical explosion. High motion, intense particle \
effects, high contrast, rapid destruction, challenging for motion estimation."
    },
    {
      "complexity": "High",
      "timestamp_range": "17:21 - 17:40",
      "description": "Black Adam emerges and attacks soldiers in the dark cave. Very fast action, significant \
magical/electrical CGI effects, low light conditions with high contrast highlights, multiple moving figures."
    }
  ]
}

"""


def _initialize_genai_client() -> genai.Client:
    """Initialize the Google Generative AI client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    return genai.Client(api_key=api_key)


def _aggregate_analysis_results(all_results: List[Dict[str, Any]], chunk_durations: List[float]) -> Dict[str, Any]:
    """
    Aggregate analysis results from multiple chunks using duration-weighted averaging.

    Args:
        all_results: List of parsed analysis results from different chunks
        chunk_durations: List of durations (in seconds) for each analyzed chunk

    Returns:
        Combined analysis result
    """
    print("Aggregating analysis results from multiple chunks...")

    if not all_results:
        raise ValueError("No analysis results to aggregate")

    # Normalize chunk durations to get weights
    total_duration = sum(chunk_durations)
    if total_duration == 0:
        # Equal weights if durations are unknown
        weights = [1.0 / len(chunk_durations) for _ in chunk_durations]
    else:
        weights = [duration / total_duration for duration in chunk_durations]

    print(f"Using weights for aggregation: {weights}")

    # Initialize combined result structure based on first result
    combined_result = {"assessment": {}, "representative_segments": []}

    # Numerical characteristics to aggregate
    characteristics = [
        "motion_intensity",
        "temporal_complexity",
        "spatial_complexity",
        "scene_change_frequency",
        "texture_detail_prevalence",
        "contrast_levels",
        "grain_noise_levels",
    ]

    # Weighted average for numerical scores
    for char in characteristics:
        weighted_score = 0.0
        weighted_justifications = []

        for i, result in enumerate(all_results):
            if "assessment" in result and char in result["assessment"]:
                char_data = result["assessment"][char]
                score = float(char_data.get("score", 0))
                justification = char_data.get("justification", "")

                weighted_score += score * weights[i]
                if justification:
                    weighted_justifications.append(f"Chunk {i + 1}: {justification}")

        # Create aggregated characteristic
        combined_result["assessment"][char] = {
            "score": round(weighted_score, 1),  # Round to one decimal
            "justification": " ".join(weighted_justifications),
        }

    # Handle animation type (non-numerical)
    animation_types = {}
    for i, result in enumerate(all_results):
        if "assessment" in result and "animation_type" in result["assessment"]:
            anim_type = result["assessment"]["animation_type"].get("type", "Unknown")
            if anim_type in animation_types:
                animation_types[anim_type] += weights[i]
            else:
                animation_types[anim_type] = weights[i]

    # Select animation type with highest weight
    if animation_types:
        majority_type = max(animation_types.items(), key=lambda x: x[1])[0]
        type_justifications = []

        for i, result in enumerate(all_results):
            if "assessment" in result and "animation_type" in result["assessment"]:
                justification = result["assessment"]["animation_type"].get("justification", "")
                if justification:
                    type_justifications.append(f"Chunk {i + 1}: {justification}")

        combined_result["assessment"]["animation_type"] = {
            "type": majority_type,
            "justification": " ".join(type_justifications),
        }

    # Combine and deduplicate representative segments
    all_segments = []
    for result in all_results:
        segments = result.get("representative_segments", [])
        for segment in segments:
            all_segments.append(segment)

    # Select diverse segments by complexity
    complexity_categories = {"Low": [], "Medium": [], "High": [], "Ultra-high": []}

    for segment in all_segments:
        complexity = segment.get("complexity", "Unknown")
        if complexity in complexity_categories:
            complexity_categories[complexity].append(segment)

    # Take best segments from each complexity category
    selected_segments = []

    # If we have segments in all categories, select top ones
    for category in ["Low", "Medium", "High", "Ultra-high"]:
        category_segments = complexity_categories[category]
        if category_segments:
            # Sort by description length as a heuristic for quality of description
            category_segments.sort(key=lambda x: len(x.get("description", "")), reverse=True)
            # Take up to 2 segments from each category, prioritizing higher complexities
            max_per_category = 3 if category in ["High", "Ultra-high"] else 1
            selected_segments.extend(category_segments[:max_per_category])

    # Limit to a reasonable number (5-7 segments)
    if len(selected_segments) > 7:
        # Prioritize High and Medium complexity if we need to reduce
        categorized = {"High": [], "Medium": [], "Low": [], "Ultra-high": []}
        for seg in selected_segments:
            categorized[seg.get("complexity", "Medium")].append(seg)

        # Rebuild with priority
        selected_segments = []
        selected_segments.extend(categorized["High"][:3])  # Up to 3 High
        selected_segments.extend(categorized["Ultra-high"][:2])  # Up to 2 Ultra-high
        selected_segments.extend(categorized["Medium"][:1])  # Up to 1 Medium
        selected_segments.extend(categorized["Low"][:1])  # Up to 1 Low

    combined_result["representative_segments"] = selected_segments

    print(f"Successfully aggregated results from {len(all_results)} chunks")
    return combined_result


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
                    f"Existing file {video_file.name} is not ACTIVE (State: {video_file.state.name}). Will re-upload."
                )
                video_file = None  # Reset video_file to trigger upload

        except Exception as e:
            print(f"Failed to retrieve or process existing file URI {existing_uri}: {e}. Will attempt upload.")
            video_file = None  # Reset video_file to trigger upload

    # 2. Upload if no valid existing file found
    if video_file is None:
        if not os.path.exists(video_path):
            print(f"Error: Local video file not found for upload: {video_path}")
            return None  # Cannot upload if local file is missing

        print(f"Uploading {video_path} to Gemini API...")
        try:
            video_file = client.files.upload(file=video_path)
            print(f"Uploaded file: {video_file.name} (State: {video_file.state.name})")
        except Exception as e:
            print(f"Error uploading file {video_path}: {e}")
            return None  # Upload failed

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


# Helper function to format seconds into SS.sss format
def format_seconds(seconds: float) -> str:
    """Formats seconds into a string with millisecond precision."""
    return f"{seconds:.3f}"


# Copied from segment_selector.py for self-containment
def _parse_timestamp(timestamp_str: str) -> float:
    """
    Parse a timestamp string into seconds.
    Handles formats like "HH:MM:SS.ms", "MM:SS.ms", or just "SS.ms".
    """
    parts = timestamp_str.strip().split(":")
    try:
        if len(parts) == 3:  # HH:MM:SS.ms
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:  # MM:SS.ms
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:  # SS.ms
            return float(parts[0])
        else:
            raise ValueError(f"Invalid timestamp format: {timestamp_str}")
    except ValueError as e:
        print(f"Warning: Could not parse timestamp '{timestamp_str}': {e}. Returning 0.0")
        return 0.0


def _map_to_content_analysis(analysis_data: Dict[str, Any]) -> ContentAnalysis:
    """Map raw analysis data to ContentAnalysis model."""
    # Corrected key from "video_assessment" to "assessment"
    assessment = analysis_data.get("assessment", {})

    return ContentAnalysis(
        motion_intensity=ContentCharacteristic(
            score=float(assessment.get("motion_intensity", {}).get("score", 0)),
            justification=assessment.get("motion_intensity", {}).get("justification", ""),
        ),
        temporal_complexity=ContentCharacteristic(
            score=float(assessment.get("temporal_complexity", {}).get("score", 0)),
            justification=assessment.get("temporal_complexity", {}).get("justification", ""),
        ),
        spatial_complexity=ContentCharacteristic(
            score=float(assessment.get("spatial_complexity", {}).get("score", 0)),
            justification=assessment.get("spatial_complexity", {}).get("justification", ""),
        ),
        scene_change_frequency=ContentCharacteristic(
            score=float(assessment.get("scene_change_frequency", {}).get("score", 0)),
            justification=assessment.get("scene_change_frequency", {}).get("justification", ""),
        ),
        texture_detail_prevalence=ContentCharacteristic(
            score=float(assessment.get("texture_detail_prevalence", {}).get("score", 0)),
            justification=assessment.get("texture_detail_prevalence", {}).get("justification", ""),
        ),
        contrast_levels=ContentCharacteristic(
            score=float(assessment.get("contrast_levels", {}).get("score", 0)),
            justification=assessment.get("contrast_levels", {}).get("justification", ""),
        ),
        animation_type=AnimationType(
            type=assessment.get("animation_type", {}).get("type", "Unknown"),
            justification=assessment.get("animation_type", {}).get("justification", ""),
        ),
        grain_noise_levels=ContentCharacteristic(
            score=float(assessment.get("grain_noise_levels", {}).get("score", 0)),
            justification=assessment.get("grain_noise_levels", {}).get("justification", ""),
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

    # Initialize chunk_uri_map and chunk_start_times if they are None
    if state.chunk_uri_map is None:
        print("Warning: chunk_uri_map not found in state, initializing.")
        state.chunk_uri_map = {}
    if state.chunk_start_times is None:  # Should be initialized by splitter now
        print("Warning: chunk_start_times not found in state, initializing.")
        state.chunk_start_times = {}

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
            selected_chunk_indices.add(num_chunks // 2)  # Middle chunk
        if num_chunks > 1:
            selected_chunk_indices.add(num_chunks - 1)  # Last chunk

        chunks_to_analyze = [state.chunk_paths[i] for i in sorted(list(selected_chunk_indices))]
        print(f"Selected chunks for analysis: {chunks_to_analyze}")

        # Store chunk durations for weighted averaging
        chunk_durations = []

        # Process selected chunks
        all_results = []
        for chunk_path in chunks_to_analyze:
            print(f"--- Processing video chunk: {chunk_path} ---")

            # --- Get Chunk Start Time Offset ---
            chunk_start_offset = state.chunk_start_times.get(chunk_path)
            if chunk_start_offset is None:
                print(f"Warning: Could not find start time for chunk {chunk_path}. Assuming 0.0 offset.")
                chunk_start_offset = 0.0
            else:
                print(f"Chunk starts at offset: {chunk_start_offset:.3f} seconds")
            # --- End Get Chunk Start Time Offset ---

            # Get existing URI or None
            existing_uri = state.chunk_uri_map.get(chunk_path)

            # Try to get existing file or upload new one
            video_file = _get_or_upload_video(client, chunk_path, existing_uri)

            if not video_file:
                # Error handled within _get_or_upload_video, skip analysis for this chunk
                print(f"Skipping analysis for chunk {chunk_path} due to file processing error.")
                # Add a placeholder duration if skipping? For now, let's handle mismatch later.
                # chunk_durations.append(0) # Or a better estimate
                continue  # Move to the next chunk

            # Store the URI in the state map if it's not already there or if it was just uploaded
            if chunk_path not in state.chunk_uri_map or state.chunk_uri_map.get(chunk_path) != video_file.uri:
                print(f"Updating state map: {chunk_path} -> {video_file.uri}")
                state.chunk_uri_map[chunk_path] = video_file.uri

            # Get chunk duration (if available)
            chunk_duration = 0
            try:
                # If ffprobe is available, use it to get duration
                import subprocess

                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        chunk_path,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                chunk_duration = float(result.stdout.strip())
                print(f"Chunk duration: {chunk_duration} seconds")
            except Exception as dur_e:
                print(f"Warning: Could not determine chunk duration: {dur_e}")
                # Use file size as a fallback weight
                try:
                    chunk_duration = os.path.getsize(chunk_path)
                    print(f"Using file size as weight: {chunk_duration} bytes")
                except Exception:
                    # Default to 1 if we can't get file size either
                    chunk_duration = 1
                    print("Using default weight: 1")

            chunk_durations.append(chunk_duration)

            # Analyze with Gemini using the ACTIVE file
            print(f"Requesting analysis from Gemini for {video_file.uri}...")
            try:
                analysis_text = _analyze_with_gemini(client, video_file)
                print("Received analysis response from Gemini.")
            except Exception as analysis_e:
                print(f"Error during Gemini analysis for {video_file.uri}: {analysis_e}")
                # Skip this chunk's result but continue with others
                continue

            # Parse the response
            print("Parsing analysis response...")
            try:
                analysis_data = _parse_analysis_result(analysis_text)
                print("Analysis response parsed successfully.")

                # --- Adjust Segment Timestamps ---
                if "representative_segments" in analysis_data:
                    print(
                        f"Adjusting timestamps for {len(analysis_data['representative_segments'])} segments by {chunk_start_offset:.3f}s..."
                    )
                    adjusted_segments = []
                    for raw_seg in analysis_data["representative_segments"]:
                        try:
                            ts_range = raw_seg.get("timestamp_range", "0 - 0")
                            start_str, end_str = ts_range.split(" - ")
                            # Parse chunk-relative times
                            chunk_rel_start = _parse_timestamp(start_str)
                            chunk_rel_end = _parse_timestamp(end_str)

                            # Calculate absolute times
                            abs_start = chunk_rel_start + chunk_start_offset
                            abs_end = chunk_rel_end + chunk_start_offset

                            # Update the segment dictionary with absolute times string
                            raw_seg["timestamp_range"] = f"{format_seconds(abs_start)} - {format_seconds(abs_end)}"
                            adjusted_segments.append(raw_seg)
                            print(
                                f"  Adjusted segment: {raw_seg.get('description', 'N/A')[:30]}... -> {raw_seg['timestamp_range']}"
                            )

                        except Exception as seg_e:
                            print(f"  Warning: Could not parse/adjust segment timestamp '{ts_range}': {seg_e}")
                            adjusted_segments.append(raw_seg)  # Keep original if parsing fails

                    analysis_data["representative_segments"] = adjusted_segments
                # --- End Adjust Segment Timestamps ---

                print("--- Parsed and Adjusted Gemini Analysis Data ---")
                print(json.dumps(analysis_data, indent=2))
                print("---------------------------------------------")
                all_results.append(analysis_data)

            except ValueError as parse_e:
                print(f"Error parsing analysis result for {chunk_path}: {parse_e}")
                continue  # Skip if parsing fails

            print(f"--- Finished processing chunk: {chunk_path} ---")

        # Combine results using weighted averaging
        print("Combining analysis results...")
        if all_results:
            # Ensure chunk_durations has the same length as all_results
            if len(chunk_durations) != len(all_results):
                print(
                    f"Warning: Mismatch between results ({len(all_results)}) and durations ({len(chunk_durations)}). Using equal weights for aggregation."
                )
                # Fallback to equal weights if durations are inconsistent
                num_results = len(all_results)
                if num_results > 0:
                    chunk_durations = [1.0] * num_results  # Use dummy durations for the function call
                else:
                    chunk_durations = []  # Handle case with zero results

            # Use the aggregation function for weighted averaging
            result = _aggregate_analysis_results(all_results, chunk_durations)  # Aggregation uses adjusted data now
            print("Results aggregated successfully.")

            # Map aggregated result to ContentAnalysis model
            print("Mapping aggregated data to ContentAnalysis model...")
            content_analysis = _map_to_content_analysis(result)
            print("Mapping successful.")

            # Extract and map representative segments (using absolute timestamps)
            print("Extracting and mapping representative segments (with absolute timestamps)...")
            raw_segments = result.get("representative_segments", [])
            selected_segments: List[Segment] = []
            for raw_seg in raw_segments:
                try:
                    timestamp_range = raw_seg.get("timestamp_range", "0.000 - 0.000")  # Use adjusted range
                    # Parse the already absolute timestamps
                    start_str, end_str = timestamp_range.split(" - ")
                    start_time = _parse_timestamp(start_str)  # Should handle "SS.sss" format
                    end_time = _parse_timestamp(end_str)

                    segment = Segment(
                        complexity=raw_seg.get("complexity", "Unknown"),
                        timestamp_range=timestamp_range,  # Store the absolute range string
                        description=raw_seg.get("description", ""),
                        start_time=start_time,  # Store absolute start time
                        end_time=end_time,  # Store absolute end time
                    )
                    selected_segments.append(segment)
                except Exception as seg_e:
                    print(f"Warning: Could not parse final segment data: {raw_seg}. Error: {seg_e}")
            print(f"Extracted {len(selected_segments)} segments with absolute times.")

            # Update state
            print("Updating state with content analysis and selected segments...")
            state.content_analysis = content_analysis
            state.selected_segments = selected_segments
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
