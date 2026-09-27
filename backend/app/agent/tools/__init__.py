"""OpenCV 5 tool library for TrayAgent. Every tool is a pure function."""

from app.agent.tools.assess_quality import QualityResult, assess_quality
from app.agent.tools.compare_previous import CompareResult, compare_previous
from app.agent.tools.detect import DetectResult, detect
from app.agent.tools.rectify_tray import RectifyResult, rectify_tray
from app.agent.tools.reduce_glare import GlareResult, reduce_glare
from app.agent.tools.render_evidence import EvidenceSheet, render_evidence
from app.agent.tools.tile_detect import TileResult, tile_detect
from app.agent.tools.zoom_recount import ZoomResult, regions_from_dets, zoom_recount

TOOL_NAMES = (
    "assess_quality",
    "rectify_tray",
    "detect",
    "tile_detect",
    "zoom_recount",
    "reduce_glare",
    "compare_previous",
    "render_evidence",
)

__all__ = [
    "TOOL_NAMES",
    "CompareResult",
    "DetectResult",
    "EvidenceSheet",
    "GlareResult",
    "QualityResult",
    "RectifyResult",
    "TileResult",
    "ZoomResult",
    "assess_quality",
    "compare_previous",
    "detect",
    "rectify_tray",
    "reduce_glare",
    "regions_from_dets",
    "render_evidence",
    "tile_detect",
    "zoom_recount",
]
