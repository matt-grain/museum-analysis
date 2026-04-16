"""Vulture whitelist — references to intentional 'unused' names.

Vulture does not see external consumers. This file lists names that look
unused from inside the codebase but are required by framework contracts
or loaded by runtime entry points.
"""

from museums.main import app, lifespan

_ = app  # uvicorn entry point: `uvicorn museums.main:app`
_ = lifespan  # FastAPI lifespan callback
