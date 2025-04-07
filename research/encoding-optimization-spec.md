# AI-Driven Video Encoding Optimization System Specification

## 1. Overview

### 1.1 Purpose
This document specifies an AI agent system that optimizes video encoding parameters based on content analysis. The system uses a Multimodal LLM to analyze video content, applies quality metrics to sample encodings, and generates content-aware encoding recipes that optimize bitrate allocation based on content complexity.

### 1.2 Goals
- Reduce storage and bandwidth costs by optimizing encoding parameters per title
- Allocate higher bitrates to complex, high-action content and lower bitrates to simpler content
- Maintain or improve perceived video quality while reducing overall file size
- Create a system that can operate independently from the main encoding pipeline during initial testing

### 1.3 Target Use Case
The system is designed for a streaming service that currently uses standard HLS encoding ladders from Apple specifications, with x264 CBR encoding for various resolutions and bitrates.

## 2. System Requirements

### 2.1 Hardware Requirements
- Development and testing: MacBook Pro M3
- Production: Kubernetes cluster running on Azure

### 2.2 Software Requirements
- FFmpeg with VMAF metrics built-in
- Python 3.11+
- UV (Fast Python Package Manager)
- LangChain and LangGraph for workflow orchestration
- Access to Google Gemini 2.5 Pro API

### 2.3 Input Requirements
- High-quality MP4 source files
- Optional: subtitle files for additional context

### 2.4 Output Requirements
- JSON-formatted encoding recommendations and analysis report

## 3. Architecture

### 3.1 Component Overview
The system follows a graph-based workflow architecture using LangGraph with the following primary components:

1. **InputProcessor** - Validates and processes the input video file
2. **LowResEncoder** - Creates a low-resolution preview for initial analysis
3. **ContentAnalyzer** - Uses Gemini 2.5 Pro to analyze content characteristics
4. **SegmentSelector** - Identifies representative segments for detailed analysis
5. **TestEncodingGenerator** - Creates multiple encoding variants for selected segments
6. **QualityMetricsCalculator** - Calculates VMAF, PSNR for test encodings
7. **DataAggregator** - Combines metrics and analysis into structured format
8. **RecommendationEngine** - Generates encoding parameter recommendations
9. **OutputGenerator** - Creates comprehensive JSON report

### 3.2 Component Diagram

```
InputProcessor → LowResEncoder → ContentAnalyzer → SegmentSelector → 
TestEncodingGenerator → QualityMetricsCalculator → DataAggregator → 
RecommendationEngine → OutputGenerator
```

### 3.3 State Management
Each component updates a shared state with the following key data structures:
- `video_metadata`: Basic information about the input video
- `low_res_path`: Path to the generated low-resolution video
- `content_characteristics`: Structured analysis from Gemini
- `selected_segments`: Timestamp ranges for detailed analysis
- `test_encodings`: Paths and parameters for test encodings
- `quality_metrics`: VMAF, PSNR scores for each test encoding
- `aggregated_data`: Combined metrics and content analysis
- `encoding_recommendations`: Final recommended encoding parameters

### 3.4 LangGraph Implementation
The system will use LangGraph for workflow orchestration, with each component implemented as a node in the graph. The graph will manage state transitions between components. Specifically:

- Each component will be implemented as a separate node in the LangGraph
- State will be passed between nodes as described in section 3.3
- The graph will be linear, following the component flow described in section 3.2
- Error handling will cause immediate termination of the entire process

## 4. Workflow Specification

### 4.1 Initial Setup
- Command line interface: `uv run encodex master.mp4`
- Optional parameters for customization and subtitle inclusion
- All files will be stored locally during initial implementation

### 4.2 Input Processing
- Validate input video format and quality
- Extract basic metadata (resolution, frame rate, duration)
- Store video path and metadata in state

### 4.3 Low-Resolution Encoding
- Use FFmpeg to generate a 240p preview of the entire video with low bitrate
- Ensure preview is small enough for Gemini analysis but retains sufficient detail
- Store the path to the low-resolution video in state

### 4.4 Content Analysis
- Split the 240p video into 50MB chunks
- Send each chunk separately to Gemini 2.5 Pro API
- Use the same structured prompt for each chunk
- Aggregate results from all chunks using weighted averaging
- Focus on identifying:
  - Content type (cartoon, sports, action, drama, etc.)
  - Grain/noise levels
  - Presence of high-action scenes
  - Overall compression complexity
- Extract and store the following content characteristics (scored 0-100):
  - Motion intensity
  - Temporal complexity
  - Spatial complexity
  - Scene change frequency
  - Texture detail prevalence
  - Contrast levels
  - Animation type classification
  - Grain/noise levels

### 4.5 Segment Selection
- Use scene detection to identify distinct scenes when possible
- Fall back to time-based sampling if scene detection is problematic
- Select ~1 minute clips from representative scenes
- Select segments that represent various complexity levels
- Define timestamp ranges for detailed analysis (maximum 60 seconds per segment)
- Store selected segments in state

### 4.6 Test Encoding Generation
- Implement an adaptive testing strategy to minimize test encodings
- For each selected segment:
  - Start with a small set of encoding variants (2-3 resolution/bitrate combinations)
  - Add additional test points only in areas where quality changes significantly
  - Use FFmpeg with various encoding parameters
  - Store paths and parameters for each test encoding

### 4.7 Quality Metrics Calculation
- For each test encoding:
  - Calculate VMAF score against the original
  - Calculate PSNR or other relevant metrics
  - Plot quality vs. bitrate to identify points close to the convex hull
  - Store quality metrics per encoding in state

### 4.8 Data Aggregation
- Combine content characteristics and quality metrics
- Apply weighted scoring to content characteristics
- Categorize content into complexity categories:
  - Low complexity
  - Medium complexity
  - High complexity
  - Ultra-high complexity
- Store aggregated data in state

### 4.9 Recommendation Generation
- Format aggregated data for LLM processing
- Send to Google Gemini with specialized prompt
- Generate encoding parameter recommendations for:
  - Resolutions
  - Bitrates (as percentage adjustments from baseline)
- Focus on encoding parameters that approach the convex hull of the quality-bitrate curve
- Store recommendations in state

### 4.10 Output Generation
- Create a JSON report focusing on the encoding ladder, including:
  - Input video metadata
  - Content characteristics and scores
  - Complexity category
  - Recommended encoding parameters (resolution, bitrate, profile)
  - Estimated file size impact compared to baseline
- Example output format:
```json
{
  "input_file": "master.mp4",
  "metadata": {
    "duration": "01:45:23",
    "original_resolution": "1920x1080",
    "fps": 24
  },
  "content_analysis": {
    "complexity_category": "High",
    "motion_intensity": 85,
    "spatial_complexity": 72
  },
  "encoding_ladder": [
    {
      "resolution": "1920x1080",
      "bitrate": "6000k",
      "profile": "high"
    },
    {
      "resolution": "1280x720",
      "bitrate": "4500k",
      "profile": "high"
    },
    {
      "resolution": "854x480",
      "bitrate": "2500k",
      "profile": "main"
    },
    {
      "resolution": "640x360",
      "bitrate": "1000k",
      "profile": "main"
    },
    {
      "resolution": "426x240",
      "bitrate": "400k",
      "profile": "baseline"
    }
  ],
  "baseline_comparison": {
    "estimated_savings": "18%"
  }
}
```

## 5. Content Analysis Specification

### 5.1 Initial Analysis Parameters
The system will analyze the following content characteristics using Gemini 2.5 Pro:

| Characteristic | Score Range | Description |
|----------------|-------------|-------------|
| Motion intensity | 0-100 | Level of movement within scenes |
| Temporal complexity | 0-100 | How much content changes between frames |
| Spatial complexity | 0-100 | Level of detail within frames |
| Scene change frequency | 0-100 | Frequency and abruptness of scene transitions |
| Texture detail | 0-100 | Presence of fine textures and patterns |
| Contrast levels | 0-100 | Dynamic range within the content |
| Animation type | Category | Live action, CGI, 2D animation, etc. |
| Grain/noise levels | 0-100 | Presence of film grain or visual noise |

### 5.2 Gemini Prompt Template
```
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
```

## 6. Encoding Decision System

### 6.1 Complexity Categorization
The system will use a weighted scoring approach to categorize content:

- Assign weights to each content characteristic based on industry expertise
- Calculate weighted average of content characteristics
- Categorize into:
  - Low complexity: 0-25
  - Medium complexity: 26-50
  - High complexity: 51-75
  - Ultra-high complexity: 76-100

### 6.2 Encoding Parameter Adjustment
- For each complexity category, apply percentage adjustments to baseline bitrates
- Focus on identifying points close to the convex hull of quality vs. bitrate
- Rather than fixed VMAF thresholds, optimize for the most efficient quality-to-bitrate ratio
- Specific adjustment percentages will be determined through experimentation
- Example framework:
  - Low complexity: Reduce bitrates by X%
  - Medium complexity: Use baseline bitrates
  - High complexity: Increase bitrates by Y%
  - Ultra-high complexity: Increase bitrates by Z%

### 6.3 Recommendation Generation Prompt
```
Based on the provided content analysis and quality metrics, recommend optimal 
encoding parameters for this video content. The content has been categorized as 
[COMPLEXITY_CATEGORY].

Consider the following factors:
1. Content characteristics: [CHARACTERISTICS_JSON]
2. Quality metrics for test encodings: [METRICS_JSON]

Provide recommendations for:
1. Resolution ladder adjustments (if any)
2. Bitrate adjustments as percentages from baseline values
3. Justification for recommendations
4. Expected impact on file size and perceived quality

Format the response as structured JSON.
```

## 7. Evaluation Framework

### 7.1 Success Metrics
- File size reduction compared to baseline encodings
- User perception of video quality
- Processing time and resource utilization

### 7.2 Testing Methodology
- Initial testing will be manual with human review of recommendations
- Comparison of file sizes between standard and optimized encodings
- Visual comparison of encoding quality

## 8. Error Handling

### 8.1 Error Handling Approach
- The system will immediately halt the entire process upon any component failure
- No retry mechanisms will be implemented in the initial version
- Error messages will be detailed and specific to help diagnose issues
- All errors will be logged with relevant context information

## 9. Implementation Plan

### 9.1 Phase 1: Prototype Development
- Implement standalone command-line tool
- Manual review of encoding recommendations
- Focus on core workflow and LLM integration
- Manual analysis of results

### 9.2 Phase 2: Integration
- Integration with existing encoding workflow
- Automated parameter adjustment
- Performance optimization
- Production deployment

## 10. Future Enhancements

### 10.1 Potential Improvements
- Machine learning model to replace rule-based scoring
- Expanded content characteristic analysis
- Support for additional encoding formats and parameters
- Real-time encoding adjustment during live streaming
- Automated A/B testing framework
- Cloud storage integration

## 11. Appendix

### 11.1 Baseline HLS Encoding Ladder
```
[Apple HLS recommended encoding ladder would be included here]
```

### 11.2 FFmpeg Command Templates
```
# Low-resolution preview generation
ffmpeg -i [INPUT] -vf scale=-1:240 -c:v libx264 -crf 23 -preset fast [OUTPUT]

# Test encoding generation
ffmpeg -i [INPUT] -ss [START] -t [DURATION] -c:v libx264 -b:v [BITRATE] -maxrate [MAXRATE] -bufsize [BUFSIZE] [OUTPUT]

# VMAF calculation
ffmpeg -i [TEST_ENCODE] -i [REFERENCE] -lavfi libvmaf=log_fmt=json:log_path=[OUTPUT_JSON] -f null -
```
