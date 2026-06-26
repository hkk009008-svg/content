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
| `attestation_revoked` | `live` | `scripts/seat_emit.py <seat> attestation_revoked`<br>`scripts/chief_emit.py <chief> attestation_revoked`<br>`scripts/overseer_emit.py attestation_revoked` | `tests/unit/test_threeway_seat_emit.py`<br>`tests/unit/test_threeway_chief_emit.py`<br>`tests/unit/test_threeway_overseer_emit.py`<br>`tests/unit/test_threeway_t2_t3_emitters_e2e.py` | principal-safe revocation CLIs |
| `brief` | `live` | `scripts/overseer_emit.py brief` | `tests/unit/test_threeway_overseer_emit.py` | overseer-authority fact |
| `brief_superseded` | `live` | `scripts/overseer_emit.py brief_superseded` | `tests/unit/test_threeway_overseer_emit.py`<br>`tests/unit/test_threeway_tier.py` | overseer supersession CLI |
| `candidate` | `live` | `scripts/seat_emit.py coordinator candidate`<br>`scripts/seat_emit.py coordinator2 candidate` | `tests/unit/test_threeway_seat_emit.py` | interactive coordinator fact |
| `candidate_aborted` | `live` | `scripts/seat_emit.py coordinator candidate_aborted`<br>`scripts/seat_emit.py coordinator2 candidate_aborted` | `tests/unit/test_threeway_seat_emit.py` | interactive coordinator abort fact |
| `ci_result` | `live` | `scripts/sign_ci_result.py` | `tests/unit/test_threeway_e2e_walking_skeleton.py` | CI attestor fact |
| `co_sign` | `live` | `scripts/seat_emit.py operator2 co_sign` | `tests/unit/test_threeway_seat_emit.py`<br>`tests/unit/test_threeway_t2_t3_emitters_e2e.py` | dynamic mirror-verifier CLI |
| `cycle_go` | `live` | `scripts/overseer_emit.py cycle_go` | `tests/unit/test_threeway_overseer_emit.py` | overseer cycle authorization |
| `human_approval` | `live` | `scripts/chief_emit.py <chief> human_approval` | `tests/unit/test_threeway_chief_emit.py`<br>`tests/unit/test_threeway_t2_t3_emitters_e2e.py` | rostered chief approval CLI |
| `merge_completed` | `live` | `threeway/gate.py run_gate` | `tests/unit/test_threeway_e2e_walking_skeleton.py` | merge-gate completion fact |
| `re_verify` | `live` | `scripts/seat_emit.py operator re_verify` | `tests/unit/test_threeway_seat_emit.py`<br>`tests/unit/test_threeway_t2_t3_emitters_e2e.py` | candidate primary-verifier challenge echo CLI |
| `re_verify_challenge` | `live` | `scripts/overseer_emit.py re_verify_challenge` | `tests/unit/test_threeway_overseer_emit.py` | overseer nonce challenge |
| `release_order` | `live` | `scripts/overseer_emit.py release_order` | `tests/unit/test_threeway_overseer_emit.py` | manual overseer release order |
| `release_requested` | `live` | `scripts/seat_emit.py coordinator release_requested`<br>`scripts/seat_emit.py coordinator2 release_requested` | `tests/unit/test_threeway_seat_emit.py` | interactive coordinator release request |
