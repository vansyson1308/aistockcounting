"""Appearance embeddings for tracking (plan sections H/I; Gate 0A section 9).

Real crops from real video only — synthetic embeddings are never used for
gate evidence. Backbones are pluggable; torch is imported lazily so the rest
of ml/ stays importable in torch-less environments.
"""
