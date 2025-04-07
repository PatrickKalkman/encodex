# EncodEx: AI-Driven Video Encoding Optimization System

EncodEx is a system that uses AI to analyze video content and generate optimized encoding parameters based on content complexity. It leverages Google's Gemini 2.5 Pro for video content analysis and implements a LangGraph-based workflow for step-by-step processing.

## Features

- Analyzes video content characteristics using Google Gemini 2.5 Pro
- Extracts metadata and creates low-resolution previews
- Selects representative segments for encoding tests
- Generates and evaluates test encodings with quality metrics
- Recommends optimal encoding parameters based on content complexity
- Provides estimated storage savings compared to standard encoding ladders

## Installation

### Prerequisites

- Python 3.11 or higher
- FFmpeg installed and available in your PATH
- Google Gemini API key

### Install from source

```bash
# Clone the repository
git clone https://github.com/yourusername/encodex.git
cd encodex

# Install using pip
pip install -e .
```

### Environment Setup

Set up your Google Gemini API key:

```bash
export GEMINI_API_KEY=your_api_key_here
```

## Usage

### Running the Workflow

To run the complete workflow:

```bash
encodex workflow --input path/to/video.mp4 --output results.json
```

### Testing Individual Nodes

You can test individual nodes in the workflow:

```bash
# Process input and extract metadata
encodex node input_processor --input path/to/video.mp4 --output state1.json

# Create low-resolution preview
encodex node low_res_encoder --state state1.json --output state2.json

# Analyze content with Gemini
encodex node content_analyzer --state state2.json --output state3.json
```

### Legacy Commands

For backward compatibility with the original implementation:

```bash
# Analyze directly with Gemini
encodex analyze path/to/video.mp4

# List uploaded files
encodex list-files

# Delete all uploaded files
encodex delete-files
```

## Project Structure

```
encodex/
├── __init__.py           # Package initialization
├── cli.py                # Command-line interface
├── graph.py              # LangGraph workflow definition
├── graph_state.py        # State management and data models
├── node_runner.py        # Utilities for running individual nodes
└── nodes/                # Node implementations
    ├── __init__.py
    ├── input_processor.py
    ├── low_res_encoder.py
    ├── content_analyzer.py
    ├── segment_selector.py
    └── placeholder_nodes.py
```

## Development Status

This project is under active development. Currently implemented nodes:

- [x] InputProcessor - Validates and extracts metadata from input video
- [x] LowResEncoder - Creates a low-resolution preview for analysis
- [x] ContentAnalyzer - Uses Google Gemini to analyze content characteristics
- [x] SegmentSelector - Identifies representative segments (basic implementation)
- [ ] TestEncodingGenerator - Creates test encodings (placeholder)
- [ ] QualityMetricsCalculator - Calculates quality metrics (placeholder)
- [ ] DataAggregator - Combines metrics and analysis (placeholder)
- [ ] RecommendationEngine - Generates encoding recommendations (placeholder)
- [ ] OutputGenerator - Creates final output report (placeholder)

## License

[MIT](LICENSE)
