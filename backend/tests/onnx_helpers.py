"""Build tiny ONNX graphs whose output is a fixed YOLOX-shaped tensor.

This lets the cv2.dnn load, forward and decode path be tested with no
trained weights. The graph computes ``C + 0 * mean(input)``, so OpenCV has to
run a real forward pass.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def yolox_constant_output(
    input_hw: tuple[int, int] = (64, 64),
    strides: tuple[int, ...] = (8, 16, 32),
    num_classes: int = 1,
    hits: list[tuple[int, int, int, float]] | None = None,
) -> np.ndarray:
    """Raw (non-decoded) YOLOX output with detections at the given anchors.

    ``hits``: (stride_index, gx, gy, obj) placing a 16x16 box centered in
    that cell.
    """
    sizes = [(input_hw[0] // s) * (input_hw[1] // s) for s in strides]
    n = sum(sizes)
    out = np.zeros((1, n, 5 + num_classes), np.float32)
    out[..., 2:4] = -10.0  # tiny boxes for non-hits
    for si, gx, gy, obj in hits or []:
        stride = strides[si]
        ws = input_hw[1] // stride
        idx = sum(sizes[:si]) + gy * ws + gx
        out[0, idx, 0] = 0.5
        out[0, idx, 1] = 0.5
        out[0, idx, 2] = math.log(16 / stride)
        out[0, idx, 3] = math.log(16 / stride)
        out[0, idx, 4] = obj
        out[0, idx, 5:] = 1.0
    return out


def write_constant_model(path: Path, const: np.ndarray, input_hw=(64, 64)) -> Path:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    inp = helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, *input_hw])
    out = helper.make_tensor_value_info("output", TensorProto.FLOAT, list(const.shape))
    nodes = [
        helper.make_node("ReduceMean", ["images"], ["m"], axes=[1, 2, 3], keepdims=1),
        helper.make_node("Mul", ["m", "zero"], ["z"]),
        helper.make_node("Reshape", ["z", "shape"], ["z3"]),
        helper.make_node("Add", ["C", "z3"], ["output"]),
    ]
    inits = [
        numpy_helper.from_array(const.astype(np.float32), "C"),
        numpy_helper.from_array(np.zeros((1,), np.float32), "zero"),
        numpy_helper.from_array(np.array([1, 1, 1], np.int64), "shape"),
    ]
    graph = helper.make_graph(nodes, "yolox_const", [inp], [out], inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, str(path))
    return path
