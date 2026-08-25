"""Camera-geometry simulation for pitch coverage (plan section F.6).

Pure-Python (numpy) parametric model: sensor + lens + mount pose + pitch
dimensions in, pitch-wide fields out — px/m, expected player bbox height,
elevation angle, occlusion-severity proxy — per candidate camera
configuration. Architecture selection (plan B/C/D) is made from these
numbers plus Gate 0B field validation, never from taste.
"""
