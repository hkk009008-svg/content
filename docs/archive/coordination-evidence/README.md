# Coordination Evidence Archive

Use this folder for durable coordinator packet and evidence snapshots.

## Default Convention

Always save coordinator capacity packets and their supporting evidence under
this tree:

```text
docs/archive/coordination-evidence/<YYYY-MM-DD-short-cycle>/
```

Each bundle should use this shape:

```text
packets/   copied coordination/capacity/packets/*.json snapshots
mailbox/   copied mailbox route and verification-report evidence
handoffs/  copied handoff snapshots when they shaped the decision
evidence/  command-output notes, inventory snapshots, and other proof files
README.md  short index with the decision captured and exact next trigger
```

Do not move live packet files out of `coordination/capacity/packets/`; copy
snapshots here for future reference.

Current Wave 4 packet/evidence bundle:

```text
docs/archive/coordination-evidence/2026-06-17-wave4-product-oracle-route/
```
