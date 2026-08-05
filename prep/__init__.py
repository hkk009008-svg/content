"""Preparation modules — pipeline setup tasks that run BEFORE production.

  - topaz_upscale:   local Topaz Video AI CLI wrapper (final master upscale)

Everything in this package is opt-in. The production pipeline runs fine without
any of these — they exist to push from "good defaults" toward "tuned for max
quality" on a per-project basis.
"""
