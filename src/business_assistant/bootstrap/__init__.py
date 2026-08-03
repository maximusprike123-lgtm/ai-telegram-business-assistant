"""Application composition root added as executable adapters become available."""

from .phase3 import build_phase3_app, create_app_from_environment

__all__ = ["build_phase3_app", "create_app_from_environment"]
