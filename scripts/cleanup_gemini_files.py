#!/usr/bin/env python
"""
Script to delete files uploaded to the Gemini API based on a state JSON file.

Reads the `chunk_uri_map` from a given EncodEx state JSON file and attempts
to delete each corresponding file using the Gemini API.

Requires the `google-generativeai` library and the `GEMINI_API_KEY`
environment variable to be set.

Usage:
  python scripts/cleanup_gemini_files.py <path_to_state.json>
"""

import argparse
import json
import os
import re
import sys

from google import genai

# Regex to extract the file ID from the URI (e.g., files/xxxx -> xxxx)
# Handles both full URLs and just the 'files/...' part
GEMINI_FILE_ID_PATTERN = r"(?:files\/|v1beta\/files\/)([a-zA-Z0-9_-]+)$"


def delete_gemini_file(client: genai.Client, file_id: str) -> bool:
    """
    Deletes a single file from the Gemini API using its ID.

    Args:
        client: Initialized Gemini client.
        file_id: The ID of the file to delete (e.g., '56g3177y8461').

    Returns:
        True if deletion was successful or file didn't exist, False otherwise.
    """
    file_name = f"files/{file_id}"
    try:
        # Check if file exists first (optional, delete is idempotent)
        # client.files.get(name=file_name)

        print(f"Attempting to delete file: {file_name} ... ", end="")
        client.files.delete(name=file_name)
        print("Success.")
        return True
    except Exception as e:
        # Handle cases where the file might already be deleted or other errors
        error_message = str(e)
        if "not found" in error_message.lower():
            print(f"File {file_name} not found (already deleted?). Skipping.")
            return True  # Consider 'not found' as success in cleanup
        else:
            print(f"Failed. Error: {error_message}")
            return False


def main():
    """Main function to parse arguments and delete files."""
    parser = argparse.ArgumentParser(description="Delete Gemini files listed in an EncodEx state JSON file.")
    parser.add_argument(
        "state_file",
        help="Path to the EncodEx JSON state file containing the chunk_uri_map.",
    )
    args = parser.parse_args()

    # Check for API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    # Check if state file exists
    if not os.path.exists(args.state_file):
        print(f"Error: State file not found: {args.state_file}")
        sys.exit(1)

    # Read and parse the state file
    try:
        with open(args.state_file, "r") as f:
            state_data = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from file: {args.state_file}")
        sys.exit(1)
    except IOError as e:
        print(f"Error reading state file {args.state_file}: {e}")
        sys.exit(1)

    # Extract the chunk_uri_map
    chunk_uri_map = state_data.get("chunk_uri_map")
    if not chunk_uri_map:
        print("No 'chunk_uri_map' found in the state file. Nothing to delete.")
        sys.exit(0)
    if not isinstance(chunk_uri_map, dict):
        print("Error: 'chunk_uri_map' is not a valid dictionary.")
        sys.exit(1)

    # Initialize Gemini client
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Error initializing Gemini client: {e}")
        sys.exit(1)

    print(f"Found {len(chunk_uri_map)} file URIs in {args.state_file}.")

    success_count = 0
    fail_count = 0

    # Iterate and delete
    for local_path, uri in chunk_uri_map.items():
        if not isinstance(uri, str):
            print(f"Warning: Skipping invalid URI entry for {local_path}: {uri}")
            continue

        match = re.search(GEMINI_FILE_ID_PATTERN, uri)
        if match:
            file_id = match.group(1)
            if delete_gemini_file(client, file_id):
                success_count += 1
            else:
                fail_count += 1
        else:
            print(f"Warning: Could not extract file ID from URI: {uri}")
            fail_count += 1

    print("\nCleanup Summary:")
    print(f"  Successfully deleted (or file not found): {success_count}")
    print(f"  Failed to delete (or invalid URI): {fail_count}")

    if fail_count > 0:
        sys.exit(1)  # Exit with error code if any deletions failed


if __name__ == "__main__":
    main()
