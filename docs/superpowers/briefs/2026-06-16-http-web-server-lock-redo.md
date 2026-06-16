# R-BRIEF: http-web-server-lock-redo - lock-held HTTP mutator hardening

PRIORITY: MAJOR/MEDIUM        LANE: B (video/assembly/audio)
CROSS-CUTTING: yes (`web_server.py`)
  -> LOCK held: `env -u GIT_INDEX_FILE coordination/bin/claim-lock 2 web_server.py director2 http-clearperf-silent200` -> `WON: coordination/locks/2-web_server.py.lock` at `5dc056bd`.
  -> CO-SIGN: not required. These Wave 2 HTTP rows are Pair-B-only and are not CRITICAL cross-cutting rows.

## The defect

The remaining open Wave 2 HTTP rows are the `web_server.py` cluster:

- `http-clearperf-silent200`
- `http-drivingvid-orphan`
- `http-addchar-float-unguarded`
- `http-null-json-body`
- `http-styleboard-false201`

Operator2 found the earlier `ab7805e0` implementation functionally GO-quality, but protocol-invalid because it touched `web_server.py` before any valid `W2-web_server.py` lock provenance existed. This brief is the lock-held redo path, not a request to upgrade that earlier verdict as-is.

During redo review, the same `ip_adapter_weight` parser family has one still-live sibling gap: JSON boolean values are accepted by Python's numeric coercion (`float(True) == 1.0`) and then written as an operator weight. The desired contract is that the HTTP knob accepts finite numeric values only, not booleans.

## Rule #12 - grep-the-writes

TARGET SYMBOL: `ip_adapter_weight` dict writes in `web_server.py`

```text
$ rg -n "ip_adapter_weight|_parse_ip_adapter_weight|request\\.json|request\\.form" web_server.py tests/unit/test_discovery_web_server_xfail.py
web_server.py:115:def _parse_ip_adapter_weight(value) -> float:
web_server.py:585:        ip_weight = _parse_ip_adapter_weight(request.form.get("ip_adapter_weight", "0.85"))
web_server.py:650:            _parse_ip_adapter_weight(data["ip_adapter_weight"])
web_server.py:724:                    latest_char["ip_adapter_weight"] = ip_weight
web_server.py:1079:        data = request.json or {}
web_server.py:1092:        ip_weight = _parse_ip_adapter_weight(data.get("ip_adapter_weight", "0.85"))
web_server.py:1111:        ip_adapter_weight=ip_weight,
web_server.py:1159:    data = (request.json or {}) if request.is_json else request.form.to_dict()
web_server.py:1162:            _parse_ip_adapter_weight(data["ip_adapter_weight"])
web_server.py:1204:            latest_obj["ip_adapter_weight"] = ip_weight
```

Runtime writes are confirmed at `web_server.py:724`, `web_server.py:1111`, and `web_server.py:1204`; `api_add_object`, `api_update_character`, and `api_update_object` accept JSON bodies, so booleans are reachable without string form coercion.

## Rule #13 - symmetric / sibling audit

SHARED FENCE/FLAG/STATE: HTTP mutator input validation and `mutate_project` result handling in `web_server.py`.

```text
$ rg -n "MutationResult\\(None|return jsonify\\(\\{\\\"uploaded\\\"|return jsonify\\(\\{\\\"cleared\\\"|_json_object_or_none\\(|style-board|upload-driving-video|performance\\)" web_server.py tests/unit/test_discovery_web_server_xfail.py
web_server.py:125:def _json_object_or_none():
web_server.py:900:@app.route("/api/projects/<pid>/shots/<sid>/upload-driving-video", methods=["POST"])
web_server.py:958:        return MutationResult(None, save=False)
web_server.py:960:    saved_path = mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT, snapshot=project)
web_server.py:967:    return jsonify({"uploaded": True, "path": saved_path}), 201
web_server.py:970:@app.route("/api/projects/<pid>/shots/<sid>/performance", methods=["DELETE"])
web_server.py:1004:        return MutationResult(None, save=False)
web_server.py:1006:    cleared = mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT, snapshot=project)
web_server.py:1009:    return jsonify({"cleared": True})
web_server.py:1012:@app.route("/api/projects/<pid>/style-board", methods=["POST"])
web_server.py:1061:    refs = mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT)
web_server.py:2015:    data = _json_object_or_none()
web_server.py:2662:    data = _json_object_or_none() if request.is_json else {}
web_server.py:2710:    data = _json_object_or_none() if request.is_json else {}
```

Audited siblings:

- `api_upload_driving_video`: checks `saved_path`, removes the saved file on mutator miss, and returns 404.
- `api_clear_performance`: checks `cleared` and returns 404 on mutator miss.
- `api_upload_style_board`: rejects empty filename batches before mutation; no extra change in this redo.
- `api_update_shot_prompt`, `api_cleanup`, and `api_cleanup_all`: use `_json_object_or_none` or tolerant empty-body defaults; no extra change in this redo.
- Four `ip_adapter_weight` write sites share `_parse_ip_adapter_weight`; the redo folds the JSON boolean sibling into that chokepoint.

## Full-shape pattern reference

MIRROR: `_parse_ip_adapter_weight` at `web_server.py:115`.

Full shape: no route of its own; called inside project-scoped routes that take `<pid>` explicitly; raises `ValueError` for invalid input; callers convert `ValueError` into HTTP 400 JSON errors; successful values are finite floats written under the existing project mutator contracts. The boolean sibling should mirror that same error path.

## The fix

Files:

- `web_server.py`
- `tests/unit/test_discovery_web_server_xfail.py`

Add a focused regression that sends JSON boolean `ip_adapter_weight` values through the JSON-capable write sites, watch it fail because the current parser accepts booleans, then minimally harden `_parse_ip_adapter_weight` to reject booleans before calling `float(...)`.

Do not broaden into unrelated `web_server.py` endpoints. Do not ask operator2 to upgrade `ab7805e0` as-is; the verify request must disclose the earlier FAIL and the new lock-held commit range.

## Verification the operator/CI will run

Director2 local verification before verify request:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_web_server_xfail.py -q --tb=short
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_web_server_xfail.py::test_ip_adapter_weight_rejects_boolean_json_values --runxfail -q --tb=short
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Operator2 should verify the final lock-held diff against `5dc056bd..HEAD`, the existing focused HTTP selector, and the lock file `coordination/locks/2-web_server.py.lock`.
