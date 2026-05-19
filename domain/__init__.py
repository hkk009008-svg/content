"""Cinema Pipeline — domain models package.

Phase 8 of the architecture refactor: collect the six interdependent
project/scene/character/location modules under a single package so the
shape of the "domain" is visible from the directory layout.

  domain/project_manager.py    — project CRUD + Mutation pattern
  domain/character_manager.py  — character creation + identity anchors
  domain/location_manager.py   — location creation + prompt seeds
  domain/continuity_engine.py  — frame-to-frame consistency tracking
  domain/scene_decomposer.py   — scene → shot list decomposition
  domain/dialogue_writer.py    — multi-character dialogue generation

The legacy import paths (``from project_manager import ...`` etc.)
still work via root-level re-export shims, so external callers
(main.py, web_server.py, cinema_pipeline.py, cleanup.py, tests/) keep
running unchanged. New code should import from ``domain.*`` directly.
"""
