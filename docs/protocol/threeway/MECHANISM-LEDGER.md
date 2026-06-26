# Threeway Mechanism Ledger

Generated and checked by:

```bash
.venv/bin/python scripts/threeway_mechanism_ledger.py --check
```

| Kind | Status | Runtime emitters / support | Tests | Note |
|---|---|---|---|---|
| `approver_roster` | `live` | `scripts/overseer_emit.py approver_roster` | `tests/unit/test_threeway_overseer_emit.py` | overseer roster |
| `assignment` | `live` | `scripts/overseer_emit.py assignment` | `tests/unit/test_threeway_overseer_emit.py` | overseer assignment |
| `attestation` | `live` | `scripts/seat_emit.py operator attestation`<br>`scripts/seat_emit.py operator2 attestation` | `tests/unit/test_threeway_seat_emit.py` | primary verifier attestation |
| `attestation_revoked` | `partial` | `threeway/reducer.py` | `tests/unit/test_threeway_tier.py` | reducer support exists; CLI added in this plan |
| `brief` | `live` | `scripts/overseer_emit.py brief` | `tests/unit/test_threeway_overseer_emit.py` | overseer-authority fact |
| `brief_superseded` | `partial` | `threeway/reducer.py` | `tests/unit/test_threeway_tier.py` | reducer support exists; CLI added in this plan |
| `candidate` | `live` | `scripts/seat_emit.py coordinator candidate`<br>`scripts/seat_emit.py coordinator2 candidate` | `tests/unit/test_threeway_seat_emit.py` | interactive coordinator fact |
| `candidate_aborted` | `live` | `scripts/seat_emit.py coordinator candidate_aborted`<br>`scripts/seat_emit.py coordinator2 candidate_aborted` | `tests/unit/test_threeway_seat_emit.py` | interactive coordinator abort fact |
| `ci_result` | `live` | `scripts/sign_ci_result.py` | `tests/unit/test_threeway_e2e_walking_skeleton.py` | CI attestor fact |
| `co_sign` | `partial` | `threeway/tier.py` | `tests/unit/test_threeway_tier.py` | gate support exists; seat CLI added in this plan |
| `cycle_go` | `live` | `scripts/overseer_emit.py cycle_go` | `tests/unit/test_threeway_overseer_emit.py` | overseer cycle authorization |
| `human_approval` | `partial` | `threeway/tier.py` | `tests/unit/test_threeway_tier.py` | gate support exists; chief CLI added in this plan |
| `merge_completed` | `live` | `threeway/gate.py run_gate` | `tests/unit/test_threeway_e2e_walking_skeleton.py` | merge-gate completion fact |
| `re_verify` | `partial` | `threeway/tier.py` | `tests/unit/test_threeway_tier.py` | gate support exists; seat CLI added in this plan |
| `re_verify_challenge` | `live` | `scripts/overseer_emit.py re_verify_challenge` | `tests/unit/test_threeway_overseer_emit.py` | overseer nonce challenge |
| `release_order` | `live` | `scripts/overseer_emit.py release_order` | `tests/unit/test_threeway_overseer_emit.py` | manual overseer release order |
| `release_requested` | `live` | `scripts/seat_emit.py coordinator release_requested`<br>`scripts/seat_emit.py coordinator2 release_requested` | `tests/unit/test_threeway_seat_emit.py` | interactive coordinator release request |
