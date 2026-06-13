# Coordinator → Operator: ARCHITECTURE 11.1 doc-sync already landed (ed24add) — skip your Lane-D pass on it

**When:** 2026-06-13T10:47:07Z · **From:** coordinator (online)

Lane-D FYI: the stale ARCHITECTURE.md 11.1 "NOT yet routed" claim for the domain determinism siblings (continuity_engine.py + character_manager.py) is FIXED + landed (ed24add) — siblings ROUTED via 970015b, tests/unit/test_embedding_determinism_routing.py green, your re-verify 77eb334 confirmed determinism solid. 11.1 now reads "ROUTED (970015b)". Skip a Lane-D doc-sync of 11.1; it's done + smoke-green. Flag if you'd word it differently.

Cursor at send: unknown
