# Three-way public-key trust root

One file per seat: `<seat>.pub` — hex of the 32-byte Ed25519 **public** key.
These are committed; they are the trust root the merge-gate verifies every
load-bearing fact against.

PRIVATE keys are NEVER committed. They live in the keystore dir (env
`THREEWAY_KEYSTORE`, default `~/.threeway/keys`), one `<seat>.ed25519` per seat
(hex of the 32-byte raw seed). A private key must never be present in an
environment that executes candidate code (spec §6.4).

Slice-1 seats: `director` (Codex, builder), `operator` (Claude, primary
verifier), `coordinator` (Claude, executing integrator), `overseer`
(release_order + cycle_go), `merge-gate` (merge-completed), `ci` (signs
ci_result). Generate with `python -m threeway.keys_bootstrap` (Task 16).
