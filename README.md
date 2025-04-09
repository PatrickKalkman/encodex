# EnCodex 🎬

> _AI-Driven Video Encoding Optimization System_

> **Implementation Details:** For an in-depth look at EnCodex's architecture and development process, read our Medium article:  
> [EnCodex: How AI is Revolutionizing Video Streaming Quality](https://medium.com/ai-advances/encodex-how-ai-is-revolutionizing-video-streaming-quality-b69f0c95b8fa)

![EnCodex Cover](cover.jpg)

[![GitHub Actions Status](https://img.shields.io/github/actions/workflow/status/PatrickKalkman/encodex/ci.yml?branch=main)](https://github.com/PatrickKalkman/encodex/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/PatrickKalkman/encodex)](https://github.com/PatrickKalkman/encodex/stargazers)
[![GitHub last commit](https://img.shields.io/github/last-commit/PatrickKalkman/encodex)](https://github.com/PatrickKalkman/encodex)
[![open issues](https://img.shields.io/github/issues/PatrickKalkman/encodex)](https://github.com/PatrickKalkman/encodex/issues)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://makeapullrequest.com)

EnCodex uses AI to analyze video content and generate optimized encoding parameters based on content complexity. It leverages Google's Gemini 2.5 Pro for video content analysis and implements a LangGraph-based workflow for step-by-step processing with convex hull optimization for encoding ladders.

## Features

- 🧠 **AI Content Analysis**: Analyzes video content characteristics using Google Gemini 2.5 Pro
- 📊 **Convex Hull Optimization**: Uses the Pareto frontier approach to find optimal bitrate-quality tradeoffs
- 📼 **Per-Content Encoding**: Adjusts encoding parameters based on content complexity
- 📉 **Storage Optimization**: Provides estimated storage savings compared to standard encoding ladders
- 🔍 **Content-Aware Segments**: Selects representative segments for targeted encoding tests
- 📈 **Quality Metrics**: Evaluates encodings using VMAF and PSNR metrics

## Installation

### Prerequisites

- Python 3.11 or higher
- FFmpeg installed and available in your PATH (with VMAF support)
- Google Gemini API key

### Install from source

```bash
# Clone the repository
git clone https://github.com/PatrickKalkman/encodex.git
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

### Running the Complete Workflow

To run the end-to-end encoding optimization process:

```bash
encodex workflow --input path/to/video.mp4 --output results.json
```

### Testing Individual Nodes

You can run and test individual components of the workflow:

```bash
# Process input and extract metadata
encodex node input_processor --input path/to/video.mp4 --output state1.json

# Create low-resolution preview
encodex node low_res_encoder --state state1.json --output state2.json --use-gpu

# Analyze content with Gemini
encodex node content_analyzer --state state2.json --output state3.json

# Generate test encodings
encodex node test_encoding_generator --state state3.json --output state4.json

# Calculate quality metrics
encodex node quality_metrics_calculator --state state4.json --output state5.json

# Aggregate data and determine complexity
encodex node data_aggregator --state state5.json --output state6.json

# Generate encoding recommendations
encodex node recommendation_engine --state state6.json --output state7.json
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

## How It Works

EnCodex uses a multi-step approach to optimize video encoding:

1. **Content Analysis**: Videos are analyzed by Google's Gemini 2.5 Pro to identify motion, complexity, and scene characteristics
2. **Test Encodings**: Selected segments are encoded at various resolutions and bitrates
3. **Quality Assessment**: VMAF and PSNR metrics are calculated for each test encoding
4. **Convex Hull Optimization**: The Pareto frontier of quality-bitrate points is calculated to identify optimal encoding parameters
5. **Content-Aware Adjustments**: Encoding parameters are adjusted based on overall content complexity
6. **Encoding Ladder Generation**: A complete encoding ladder is generated with optimal resolution and bitrate pairs

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
    ├── video_splitter.py
    ├── content_analyzer.py
    ├── test_encoding_generator.py
    ├── quality_metrics_calculator.py
    ├── data_aggregator.py
    ├── recommendation_engine.py
    └── output_generator.py
```

## Development Status

All main components have been implemented:

- [x] InputProcessor - Validates and extracts metadata from input video
- [x] LowResEncoder - Creates a low-resolution preview for analysis
- [x] VideoSplitter - Splits videos for Gemini processing
- [x] ContentAnalyzer - Uses Google Gemini to analyze content characteristics
- [x] TestEncodingGenerator - Creates test encodings for different resolutions and bitrates
- [x] QualityMetricsCalculator - Calculates VMAF and PSNR metrics
- [x] DataAggregator - Combines metrics and analysis to determine content complexity
- [x] RecommendationEngine - Generates optimized encoding ladder using convex hull
- [x] OutputGenerator - Creates final JSON report with recommendations

## Contributing

Contributions are welcome! Feel free to:

- Submit issues for bugs or feature ideas
- Fork the repository and submit pull requests
- Suggest improvements to the encoding optimization algorithms

## License

[MIT](LICENSE)
