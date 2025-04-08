"""
State management for the EncodEx LangGraph.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class VideoMetadata(BaseModel):
    """Video metadata extracted from the input file."""

    path: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None


class ContentCharacteristic(BaseModel):
    """Content characteristic with score and justification."""

    score: float = Field(..., ge=0, le=100)
    justification: str


class AnimationType(BaseModel):
    """Animation type classification."""

    type: str
    justification: str


class ContentAnalysis(BaseModel):
    """Content analysis results from Gemini."""

    motion_intensity: ContentCharacteristic
    temporal_complexity: ContentCharacteristic
    spatial_complexity: ContentCharacteristic
    scene_change_frequency: ContentCharacteristic
    texture_detail_prevalence: ContentCharacteristic
    contrast_levels: ContentCharacteristic
    animation_type: AnimationType
    grain_noise_levels: ContentCharacteristic


class Segment(BaseModel):
    """Selected video segment for encoding tests."""

    complexity: str
    timestamp_range: str
    description: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class TestEncoding(BaseModel):
    """Test encoding with parameters and path."""

    path: str
    resolution: str
    bitrate: int
    segment: str  # References a segment ID


class QualityMetric(BaseModel):
    """Quality metric for a test encoding."""

    encoding_id: str  # Reference to a test encoding
    vmaf: float
    psnr: Optional[float] = None


class ComplexityCategory(str, Enum):
    """Content complexity categories."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    ULTRA_HIGH = "Ultra-high"


class EncodingParameters(BaseModel):
    """Encoding parameters for a specific resolution."""

    resolution: str
    bitrate: str
    profile: str


class EnCodexState(BaseModel):
    """Complete state for the EncodEx workflow."""

    input_file: str
    video_metadata: Optional[VideoMetadata] = None
    low_res_path: Optional[str] = None
    chunk_paths: List[str] = Field(default_factory=list)
    chunk_start_times: Dict[str, float] = Field(default_factory=dict)
    chunk_uri_map: Optional[Dict[str, str]] = Field(default_factory=dict)
    content_analysis: Optional[ContentAnalysis] = None
    selected_segments: List[Segment] = Field(default_factory=list)
    test_encodings: List[TestEncoding] = Field(default_factory=list)
    quality_metrics: List[QualityMetric] = Field(default_factory=list)
    complexity_category: Optional[ComplexityCategory] = None
    encoding_ladder: List[EncodingParameters] = Field(default_factory=list)
    estimated_savings: Optional[str] = None
    error: Optional[str] = None
