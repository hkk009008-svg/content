"""Cinema Pipeline — orchestration package.

This package is the future home for the pipeline orchestrator and its
Phase classes. Phase 5 of the architecture refactor introduces it
incrementally — the legacy `cinema_pipeline.py` god module is migrated
phase-by-phase into `cinema/phases/`.

Current contents:
  cinema.context           — PipelineContext (typed replacement for `ctx: dict`)
  cinema.phases.base       — Phase protocol + PhaseResult
  cinema.phases.generation — GenerationPhase (POC; wraps phase_a_generator)

Future expansion (each lands in its own commit):
  cinema.phases.topic, .blueprint, .audio, .assembly, .vision, .upload, .learning
  cinema.pipeline          — thin driver that iterates a list of Phase instances
"""
