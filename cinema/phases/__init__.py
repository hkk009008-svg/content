"""Cinema Pipeline — Phase implementations.

Every module in this package exposes a class implementing the `Phase`
protocol from `cinema.phases.base`. The orchestrator
(`cinema_pipeline.CinemaPipeline`) drives a list of these in order, calling
`.run(ctx)` on each directly.
"""
