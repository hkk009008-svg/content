# Failure modes — agent-agnostic (relocated)

> Relocated verbatim from `AGENTS.md` as part of the operative/provenance
> split (see `docs/protocol/migration-map-claudemd-split.md`). Loaded **on trigger**,
> not at session start. Two-tree strategy: this is the `agents` copy. During
> the add-first window the root file still holds this content; it will be stubbed once
> this destination is confirmed.

---

## Quality vs. throughput watchpoints

Moving fast through multi-task plans means some checks short-circuit.
Specific risk patterns to guard against:

| Watchpoint | What can slip through | Mitigation |
|---|---|---|
| **Concurrency in new code** | Missing locks around thread-shared state (SQLite, globals, `_*_lock` adjacent code) — spec review often misses these. | When the implementer touches thread-shared state, explicitly ask the code reviewer to check lock discipline. |
| **Public-API semantic changes** | Refactors that change prop/parameter names can be visually correct but semantically wrong. | For interface refactors, the spec reviewer must verify call-site mappings are semantically correct, not just that output matches. |
| **"Just X" with structural drift** | An implementer extends beyond a stated constraint (e.g., "only className strings" turns into local const extraction). | When an implementer deviates from a hard constraint, verify the deviation is purely additive and re-run touched tests. |
| **Plan-vs-convention naming conflicts** | A field labeled one way in plan, differently in production code. Following plan literally creates a contract mismatch. | When plan and project convention conflict, surface the choice to the operator rather than defaulting either way. |
| **Pre-existing failures masking new ones** | A flaky test failing throughout makes a new failure invisible. | Mark pre-existing failures `xfail` (or tighten tolerance) early in the branch so NEW failures stand out. |

**Pattern:** the throughput optimization is "ship when the code quality
reviewer says approve." The watchpoint is making sure the reviewer is
*checking the right things*. A reviewer prompt that doesn't mention
threading won't catch a missing lock — you have to tell them.

## Failure modes and false positives

Reviewers and tooling will sometimes be wrong. Recognizing the pattern
prevents acting on bad input.

**Reviewer false positives observed in practice:**

1. **"Missing requirement" claims that contradict upstream behavior** —
   The reviewer didn't trace upstream semantics (e.g., flagged "buffer
   not capped" when the buffer is bounded at its source). **Mitigation:**
   when a "missing requirement" claim contradicts the dispatch prompt's
   stated upstream behavior, verify with a targeted grep before fixing.

2. **Sequencing concerns based on nominal task order** — Reviewer assumed
   the plan's nominal task order; your actual dispatch order may already
   satisfy the concern. **Mitigation:** check your task tracker before
   re-arranging work.

3. **"Function X not found in module Y"** — Reviewer grepped the wrong
   file. The function lived in a sibling module. **Mitigation:** if a
   reviewer says "not found," double-check the scope you provided in
   their prompt. The answer is often one file over.

4. **Security warnings on instruction-following actions** — Automated
   scanners can flag compliant behavior (e.g., the operator/system
   prompt explicitly asks for behavior the scanner doesn't recognize).
   **Mitigation:** if your action is clearly compliant with explicit
   operator/system instructions, proceed and note the false positive.

5. **Fresh instance "tool X not available"** — Fresh instances may have
   a different tool environment than you do (different MCP servers,
   different env vars, etc.). **Mitigation:** don't require fresh
   instances to use tools you have; provide fallback instructions
   (grep + file reading instead of MCP impact analysis) in their prompt.

**Tool/environment failure modes:**

6. **Edit tools that require Read first** — Many tools (including
   Claude Code's `Edit`) require a `Read` on a file before edits.
   **Mitigation:** always read (even a small window) before the first
   edit on a file.

7. **Wrong Python interpreter** — System `python3` may lack project
   test deps; the project's venv has them. **Mitigation:** use the
   project's binary explicitly: `.venv/bin/python -m pytest ...`.

8. **Background-task completion notifications** — Async notifications
   may appear in your conversation but are NOT operator input.
   **Mitigation:** treat them as informational; don't confuse them with
   operator acknowledgement of a pending question.

**Detection pattern:** when a tool/reviewer/warning contradicts what you
already know to be true, do a quick targeted verification (single read,
single grep) before acting on the claim. A 5-second check prevents a
wrong fix that itself needs reverting.

