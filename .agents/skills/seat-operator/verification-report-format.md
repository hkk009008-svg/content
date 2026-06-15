# verification-report — format & severity reference

Read this when you are about to emit a `verification-report` and want the
field structure and severity vocabulary in front of you. The report is the
operator's load-bearing artifact: it is the *only* thing that moves a fix to
`verified` (guarantee #3), so its shape and evidence matter as much as the
verdict.

## Emit it as an artifact, never as chat (Rule #19)

A binding signal is a mailbox file, not a sentence in the conversation. Generate
it with the existing tool so the envelope/cursor are correct:

```bash
coordination/bin/send-event <from> <to> verification-report "<subject line>" <<'EOF'
<body — see skeleton below>
EOF
```

`send-event` writes the H1 header, the `**When:** … · **From:** …` envelope,
and the `Cursor at send:` footer automatically. The **kind lives in the
filename only** (`…-<from>-to-<to>-verification-report.md`); there is no in-body
kind field in protocol v6.0.

## Body skeleton

```
# <From> → <To>: Lane V verification report — commit `<sha>`      ← H1 (auto)
**When:** <ISO> · **From:** <seat> (online)                       ← envelope (auto)

VERDICT: GO            (or NITS / FAIL)

## Evidence            ← R-EVIDENCE: the command AND its output, not a claim
$ <command you ran>
→ <result>

## Findings
1. <severity> — `path/file.py:line` — <what + why> — <disposition>
2. ...

## Scope-match (CRITICAL cross-cutting only)
Landed diff matches the co-signed R-BRIEF scope (defect <id>): <yes/where it drifts>.

Cursor at send: <ISO>                                              ← footer (auto)
```

## Verdict vocabulary

| Verdict | Meaning | What it triggers |
|---|---|---|
| **GO** | Diff read, independently verified, ships. | Coordinator may set `verified`; on a cross-cutting row, delete the lock in **this same commit** (§6b). |
| **NITS** | Cosmetic concerns only — but "cosmetic" is a *claim about scope*. | Fixer addresses; you **re-read the nit-fix diff** (`git show <sha>` yourself) before upgrading NITS→GO. Never self-upgrade on the fixer's word. |
| **FAIL** | Blocking defect, scope drift vs the co-signed brief, or guarantee breach. | Fix stays unverified; lock retained. After **3 consecutive FAILs** the holder releases (anti-hostage). |

## Finding-severity vocabulary (Rule #15 disposition advisory)

| Severity | Disposition guidance |
|---|---|
| **CRITICAL** | Standalone fix preferred — do not fold into unrelated work. |
| **IMPORTANT** | Fix this cycle; fold-in acceptable if tightly scoped. |
| **MINOR** | Fold-in or advisory. |
| **INFORMATIONAL** | No-action acceptable; record for awareness. |

## Worked fragment (real shape)

```
VERDICT: GO

## Evidence
$ grep -rn 'self\.spent_usd\s*=' --include='*.py' . | grep -v /tests/
→ exactly cost_tracker.py:224 (single chokepoint — log() delegates here)

## Findings
1. INFORMATIONAL — `cost_tracker.py:224` — increment sits at the log() chokepoint;
   both log_api/log_llm delegate there → no double-count. — record only.
```

## Three reminders that ride every report

- **Verdict-ahead-of-report (Rule #21):** if a peer is blocked on a *billed*
  resource (pod running), send the dispositive **GO/NO-GO as its own event
  first**; the full evidence report follows. Don't let billing burn while you
  prose-write.
- **Lock atomicity (§6b):** on GO for a cross-cutting row, `git rm` the lock and
  stage this report (`send-event`), then commit **both in one explicit-pathspec
  commit** — `release-lock` makes a *separate* unlock commit and does NOT satisfy
  "same commit as GO."
- **Correct event kind:** a post-implementation hand-off is `verification-report`
  (a status signal), never `dispatch-claim` (a *pre*-implementation intent signal).
