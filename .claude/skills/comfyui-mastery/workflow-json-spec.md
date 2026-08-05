# ComfyUI API workflow specification

## Flat API format

ComfyUI `/prompt` receives a dictionary keyed by string node IDs:

```json
{
  "10": {
    "class_type": "LoadImage",
    "inputs": {
      "image": "uploaded-source.png"
    }
  },
  "20": {
    "class_type": "SomeConsumer",
    "inputs": {
      "image": ["10", 0]
    }
  }
}
```

Rules:

1. Node IDs and link source IDs are strings.
2. A link is `[source_node_id, zero_based_output_index]`.
3. Scalar values are passed directly and must match the live input schema.
4. `class_type` is exact and case-sensitive.
5. UI position/widget metadata is not part of the production API contract.
6. Every graph must be acyclic, type-correct, and reach its output node.

## Project builders

Do not assemble a production graph from prose. Import the tracked builder:

- `deploy/windows-flux2-klein/workflow.py` for the hash-bound image
  candidate; application code reaches it through `performance/flux2_klein.py`.
- `performance/live_portrait_workflow.py` for the pinned performance worker;
  its tracked one-frame probe must equal the builder result.

Permitted runtime substitution is limited to each builder's declared
arguments: prompt/reference names/seed/aspect/output prefix for FLUX.2, and
source filename/driving filename/duration for LivePortrait. The FLUX.2 caller
invokes its builder validation before constructing a network client. The
LivePortrait adapter currently builds only after readiness and uploads, so its
builder validates names/duration at that later boundary; do not claim those
checks occurred before I/O.

## Validation algorithm

Validation is layered:

1. The tracked candidate/worker preflight validates package/revision/model/
   workflow hashes and its graph invariants. Those role-specific validators
   prove link existence/slots/types, reachability, scalar bounds, fixed
   dimensions/envelopes, and required output shape where declared.
2. Authenticated capability readiness binds that offline/execution evidence to
   the active worker.
3. The generic application client fetches live `/object_info` after required
   uploads and checks that each `class_type` exists, required inputs are
   present, unknown inputs are absent, and non-link enum/model/filename choices
   are installed/allowed.
4. The generic live check does **not** independently prove link existence,
   output slots/types, scalar ranges, acyclicity, reachability, or dimensions;
   do not attribute the stronger package guarantees to it.
5. Probe/benchmark commands additionally require an empty/non-overlapping queue
   where their contract says so.
6. Production submits once through the durable job ledger (except the explicit
   LivePortrait compatibility path documented elsewhere).

## Common errors

| Symptom | Likely cause | Correct response |
| --- | --- | --- |
| unknown node class | wrong/missing pinned revision | block readiness; repair the tracked worker rather than installing ad hoc code |
| missing/unknown input | graph and live schema differ | update the bound contract and rerun evidence; do not drop the field silently |
| model/filename rejected | active worker inventory differs | reconcile exact model/input bytes and refetch schema |
| type/slot mismatch | invalid link | fix the builder and invalidate old evidence |
| GPU memory failure | overlapping work or unbounded media | serialize, enforce graph envelopes, stop other GPU work, and rerun the bound benchmark |
| submit timeout/unknown | acceptance cannot be determined | persist `UNKNOWN` and reconcile the same durable prompt ID; do not resubmit |
| history has no valid output | incomplete/failed execution | keep the durable attempt failed/unknown and do not publish |

## Output validation

A completed prompt is not enough. Select the expected output record, download
through the bounded authenticated client, decode the file, verify the expected
image dimensions or video container, and publish atomically. Record prompt ID,
workflow/model/package hashes, output hash, latency, GPU evidence, and artifact
version provenance.
