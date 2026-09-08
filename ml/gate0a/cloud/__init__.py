"""Gate 0A cloud execution layer (Stage 0 + 1 + 2).

Thin orchestration around the frozen Gate 0A runners so the identical code
runs on Kaggle (free GPU), Hugging Face Jobs, or any CUDA box. All outputs are
DIAGNOSTIC — NOT OFFICIAL GATE 0A VERDICT; the TEST split is never touched.
"""

CLOUD_LAYER_VERSION = "stage012-v1"
BANNER = "DIAGNOSTIC — NOT OFFICIAL GATE 0A VERDICT\nTEST SET UNTOUCHED"
