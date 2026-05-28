# Brief 2.0 — Design Advisory for Protocol Restructuring

**From:** user-principal (relayed analysis) **To:** director, operator **Status:** Advisory input for brief 2.0 design. NOT prescriptive. Decisions remain with director \+ operator \+ user-principal per existing role partition.

---

## What this advisory is

Input for two bundled goals in brief 2.0:

1. Overall tightening of the current protocol.  
2. Redesign of the test toward **insight achievement** rather than pass/fail validation.

This document gives a recommended frame and a candidate mechanism. It does not dictate rules, rule numbers, or implementation. Where a decision is yours, it is flagged. Adopt, adapt, or reject per your own evidence discipline.

---

## The core distinction — read first, hold throughout

The goal is **better-aligned agent behavior achieved by encoding intent and purpose more richly into the protocol.** It is NOT agent self-understanding in any literal sense.

Concretely:

- **In scope:** briefs and verification that carry *why* and *intent*, so an agent reasons from purpose when a spec does not cover a specific case, and so local decisions extrapolate correctly from the goal.  
- **Out of scope:** any mechanism that treats agent-generated self-description as genuine introspective self-knowledge. An agent producing text about "what it is doing and why" is generating plausible reconstruction, not reporting a true internal causal trace. Useful as signal; not to be mistaken for real self-access.

**The failure mode to avoid:** optimizing toward output that *looks like* deepening self-understanding (more elaborate rationale-talk) instead of toward *actual better-aligned behavior* (decisions that match intent). The first is easy to produce and easy to measure. The second is the goal. Do not let the protocol reward rationale-talk volume. Reward behavior that matches intent.

This is the same prevention-vs-verification / appearance-vs-substance distinction the protocol already applies elsewhere. Apply it here too.

---

## Recommended mechanism — three components

### 1\. Intent-encoding: give *why* a reliable home in the brief

Today briefs carry **what** and **how** (director-what/why, operator-how). The gap is ensuring **why/intent** reliably reaches the agent *at the decision point*, not just in the brief header.

Recommendation:

- Add a dedicated **intent field** to dispatch-level units (brief, sub-brief, or dispatch event — your call which level).  
- The intent field states: *what this serves, and what a correct outcome accomplishes for the larger goal* — in one or two concrete sentences, not abstractions.  
- Test for adequacy: could a cold-context agent, given only the intent field, correctly choose between two ambiguous implementation paths? If yes, the intent is concrete enough. If not, it is still too vague to verify against (see component 2).

**Decision for you:** which protocol level the intent field attaches to, and whether it is mandatory or conditional on dispatch complexity.

### 2\. Purpose-verification: extend the verification lane to check intent-alignment

Lane V currently checks *correctness* ("is this output right"). Add a check for *purpose-alignment* ("does this output serve the stated intent").

Key constraint: purpose-verification is only possible if intent is concrete. Vague intent ("make it good") cannot be verified. Specific intent ("serves X by doing Y") can. This is why component 1 (concrete intent-encoding) is a prerequisite for component 2\.

Recommendation:

- Purpose-verification reads the intent field, then asks whether the output advances that intent — separately from whether the output is internally correct.  
- Output can be correct-but-misaligned (does the right thing for the wrong goal) or aligned-but-incorrect (right goal, flawed execution). Both are findings. Keeping the two checks separate makes the finding-type legible.

**Decision for you:** whether this is a new lane, an extension of Lane V's existing pass, or a distinct reviewer role. Watch the token cost — a separate full pass may not justify itself; a folded check inside the existing pass may.

### 3\. Divergence-logging: make prediction-comparison a systematic insight signal

The user-requested prediction-comparison methodology (predict behavior, compare to actual, mine the difference) is the insight engine. Make it systematic rather than incidental.

The mechanism:

- Before a dispatch executes, the predicting party records the predicted behavior/outcome.  
- After execution, actual is compared to predicted.  
- **Each divergence is logged as a divergence-point** — a specific place where the agent's task-model differed from the predictor's intent-model.

The insight is not the agent understanding itself. **The insight is locating where intent-encoding was insufficient.** Every divergence-point marks a place where the brief failed to transmit intent clearly enough that behavior matched expectation. Each one is an actionable target for enriching the next brief.

Over cycles, **divergence-point frequency should decrease** as intent-encoding improves. That decreasing trend is the measurable evidence that the mechanism works. If divergence frequency does not fall over cycles, the intent-encoding is not actually improving alignment — it is producing rationale-talk without behavioral effect (the failure mode above).

**Decision for you:** divergence-point logging format, and where in the cycle the predict/compare steps sit. Recommend logging that ties each divergence to the specific brief section whose intent was insufficient, so the fix target is unambiguous.

---

## How tightening and insight-achievement connect

These two goals are not in tension. They reinforce.

Tightening the protocol \= reducing the places where an agent must guess intent. Better intent-encoding *is* a form of tightening: fewer ambiguous decision points, fewer places where the agent's task-model and the user's intent-model can diverge.

So treat tightening as **intent-clarification**, not merely rule-reduction. The divergence-points from component 3 are a direct map of where tightening is most needed — they show exactly which parts of the protocol leak intent. Tighten there first. This makes tightening evidence-driven rather than guessed, consistent with the protocol's existing emergence-from-evidence discipline.

---

## The metric to track

**Prediction-match rate**, not rationale-volume.

- Right metric: did the agent's *behavior* align with the stated intent? Measured by prediction-comparison match over cycles.  
- Wrong metric: did the agent *produce more rationale text*? This is easy to game and diverges from the goal.

If the mechanism is working, prediction-match rate rises and divergence-point frequency falls across cycles, with no increase in rationale-talk required to achieve it.

---

## Suggested path — incremental, not wholesale

Consistent with the protocol's existing N=2 codification discipline:

1. **Do not restructure everything at once.** Pilot the intent-field (component 1\) on one dispatch type. Observe.  
2. Add purpose-verification (component 2\) only after intent-encoding is concrete enough to verify against. Sequencing matters — component 2 depends on component 1\.  
3. Run divergence-logging (component 3\) alongside from the start; it costs little and produces the evidence that guides the rest.  
4. Treat any new convention as a **candidate**, not a rule, until it earns its evidence threshold per existing discipline. A new mechanism that works once is N=1, not codification-ready.  
5. Let the divergence-points tell you where to tighten next, rather than tightening speculatively.

---

## What remains a user-principal / director / operator decision

- Which protocol level the intent field attaches to.  
- Whether purpose-verification is a new lane, a Lane V extension, or a distinct role.  
- Divergence-logging format and cycle placement.  
- Codification thresholds for any new convention (existing discipline applies).  
- Whether the Tier C/D validation test resumes before or after this restructuring, or is itself redesigned under the insight-achievement frame.

This advisory recommends the frame and the mechanism. The protocol is yours. Adopt against your own evidence.

---

*End of advisory.*  
