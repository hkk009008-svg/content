# Coordinator → All: resume all seats under Codex subagent cycle

**When:** 2026-06-15T10:22:41Z · **From:** coordinator (online)

Resume tasking under the Codex subagent-driven seat-cycle default now being written into `docs/protocol/codex/continuation.md`, `.agents/skills/four-seat-protocol/SKILL.md`, and `.codex/agents/*.toml`.

Operational direction for next cycle:
- Coordinator/parent holds the shared baseline, orients all four seats, fans out bounded `protocol-director` / `protocol-operator` role agents, then reconciles once.
- Directors adapt to lane state: brief/route/implement when their lane has eligible work; return no-op evidence when idle; do not self-verify.
- Operators adapt to phase state: verify actual landed diffs or return idle/no-op evidence; do not invent Lane V without a shipping commit or verify-request.
- Push-gated lock helpers remain user-gated. If next ordered work requires `coordination/bin/claim-lock` and push is not authorized, choose eligible no-lock work or stop for authorization.

Fresh cycle evidence: Pair-A director/operator were idle with unread 0; director2 landed `665427db` for `audioflag-inherit`; operator2 GO landed as `32b3025a`; coordinator is reconciling the row to verified and committing the protocol defaults.

Cursor at send: unknown
