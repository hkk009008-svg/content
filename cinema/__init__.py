"""Cinema Pipeline — orchestration package.

Shared orchestration primitives for the interactive cinema pipeline
(driven from `web_server.py` → `cinema_pipeline.py`).

Contents:
  cinema.context     — PipelineContext (typed shared state) + get_project_setting helper
  cinema.phases.base — Phase protocol + PhaseResult
  cinema.shots       — per-shot generation controller
  cinema.lifecycle   — cancel / pause / progress service

The legacy `cinema_pipeline.CinemaPipeline` god class defines its own
Phase classes (KeyframeRenderPhase, MotionRenderPhase, PerformanceCapturePhase)
inline rather than via this package's `phases/` directory.
"""
