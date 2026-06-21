# Three-way public-key trust root

One file per seat: `<seat>.pub` — hex of the 32-byte Ed25519 **public** key.
These are committed; they are the trust root the merge-gate verifies every
load-bearing fact against.

PRIVATE keys are NEVER committed. They live in the keystore dir (env
`THREEWAY_KEYSTORE`, default `~/.threeway/keys`), one `<seat>.ed25519` per seat
(hex of the 32-byte raw seed). A private key must never be present in an
environment that executes candidate code (spec §6.4).

Default runtime signing roster: `director`, `operator`, `coordinator`,
`director2`, `operator2`, `coordinator2`, `overseer`, `ci`, `merge-gate`,
`chief-gemini`, and `chief-chatgpt`. The chief seats are the key-bound T3
human-approval signers; they need committed public keys before live operation.

Generate a non-production registry/keystore pair with
`python -m threeway.keys_bootstrap --registry <tmp-registry> --keystore <tmp-keystore>`.
Do not generate production public keys into this repo without an explicit live
provisioning ceremony, and never commit private keys.
