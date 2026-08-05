# Active Product Unification Audit — 2026-07-30

**Purpose:** Durable coverage ledger for the comprehensive product unification
plan. This document turns the read-only architecture, provider, UI/backend,
browser, dependency, prompt, and documentation audits into owned dispositions.
It covers the active cinema product. Append-only ADR/protocol history and
archived handoffs remain evidence, not rewrite targets.

**Plan:** `docs/superpowers/plans/2026-07-30-comprehensive-product-unification.md`

**Checked baseline:** `main` at `decf72ee`; implementation branch
`codex/comprehensive-unification-20260730`.

## Reproducible baseline and discovery evidence

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q
3436 passed, 2 skipped, 10 subtests passed

$ npm --prefix web test -- --run && npm --prefix web run build
14 test files / 46 tests passed; production build succeeded

$ env -u GIT_INDEX_FILE .venv/bin/python -m pip check
No broken requirements found.

$ rg -n '@app\.route' web_server.py | wc -l
66

$ rg -n '\bfetch\(' web/src --glob '*.ts' --glob '*.tsx' | wc -l
54

$ rg -n '\.ok\b' web/src --glob '*.ts' --glob '*.tsx' | wc -l
13

$ rg -n 'global_settings|api_engines|target_api|tts_provider|forced_alignment|cascade_retry_limit|face_swap' \
    web/src web_server.py domain cinema audio --glob '*.py' --glob '*.ts' --glob '*.tsx' | wc -l
256

$ rg --files config/prompts .agents/skills | wc -l
29
```

These are scope-discovery counts, not correctness or quality gates. The final
ledger must disposition each discovered active surface. Route/function-name
searches are prioritization evidence only; lack of a name-reference is not
proof that a route is behaviorally untested.

### Targeted defect and absence evidence

```text
$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
from google.genai._interactions.types import VideoContent
print(VideoContent.model_fields["data"].annotation)
PY
typing.Optional[str]

$ rg -n 'files\.get|files\.download|f\.write' gemini_omni_native.py
132: file_obj = self.client.files.get(name=video.uri)
141: file_obj = self.client.files.get(name=video.uri)
142: video_data = self.client.files.download(file=file_obj)
148: f.write(video_data)

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
import inspect, firecrawl
from firecrawl import FirecrawlApp
app = FirecrawlApp(api_key="not-used")
print(firecrawl.__version__)
print(inspect.signature(app.v2.scrape))
PY
4.27.2
(url: str, *, formats: ... ) -> firecrawl.v2.types.Document

$ rg -n 'scrape_url\(|\.scrape\(' web_research.py research_engine.py
research_engine.py:131: result = firecrawl.scrape_url(url, params={"formats": ["markdown"]})
web_research.py:74: res = app.scrape_url(url, params={"formats": ["markdown"]})

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
import inspect
from runwayml import RunwayML
sig = inspect.signature(RunwayML(api_key="not-used").character_performance.create)
print(sig.parameters["model"].annotation)
print("duration" in sig.parameters)
PY
Literal['act_two']
False

$ rg -n 'model="act_one"|"model": "act_one"|duration=' performance/act_one.py
36: model="act_one"
90: "model": "act_one"
167: "model": "act_one"

$ rg -n 'duration: int = 4|"model": "ltx-2-3-pro"|"duration": duration' ltx_native.py
99: duration: int = 4
267: "model": "ltx-2-3-pro"
268: "duration": duration

$ rg -n 'generate_openai_audio|OPENAI_AUDIO' --glob '*.py' audio domain cinema phase_*.py web_server.py
audio/voiceover.py:13: ... generate_openai_audio ...
domain/scene_decomposer.py:72: "OPENAI_AUDIO": ... "status": "live"
domain/scene_decomposer.py:132: ... "OPENAI_AUDIO" ...
domain/scene_decomposer.py:163: ... "OPENAI_AUDIO" ...

$ rg -n 'PEXELS|Pexels|pexels' --glob '*.py' config domain cinema phase_*.py web_server.py
phase_c_assembly.py:16: PEXELS_API_KEY = settings.pexels_api_key
config/settings.py:83: pexels_api_key: str
config/settings.py:125: pexels_api_key=_env("PEXELS_API_KEY")

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
import ast, pathlib
tree = ast.parse(pathlib.Path("phase_c_assembly.py").read_text())
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
          and n.name == "generate_ai_broll")
loads = sorted({n.id for n in ast.walk(fn) if isinstance(n, ast.Name)
                and isinstance(n.ctx, ast.Load)
                and n.id.startswith("char_lora_")})
print(loads)
PY
[]
```

The narrow grep scopes above support only the stated current call-path claims.
They do not prove that similarly named code is absent outside those scopes.
The final tests replace these audit probes with non-vacuous contract or
mutation coverage.

### Independent architecture challenge

A ChatGPT Pro consultation reviewed the consolidated audit without repository
secrets or source dumps. Its useful challenge was to keep containment first but
move a deliberately narrow typed truth boundary ahead of multi-adapter repair;
keep provider payloads/types separate; derive UI actions from backend authority;
retire unsupported endpoints instead of investing in them; and generate only
factual reference surfaces, not architectural rationale. The plan incorporates
those points. This consultation is advisory; live source, tests, and official
provider contracts remain authority.

## Coverage ownership

| Surface discovered by | Active owner | Required disposition | Verifier |
|---|---|---|---|
| Provider adapters and model IDs | Slices 2–6 | repaired, retained-current, date-gated, disabled/unverified, or retired | primary-source link + offline adapter fixture |
| Flask routes in `web_server.py` | Slices 1, 2, 8–12 | UI-surfaced, API-only, internal, retired, or tested unchanged | route inventory + Flask contract tests |
| UI `fetch()`/mutation sites | Slices 8–13 | typed success/error handling or explicitly read-only | frontend contract tests + no ignored non-2xx |
| Settings writes and production reads | Slice 9 | wired and validated, read-only, or removed | reciprocal write/read test |
| Project media path producers/consumers | Slice 10 | project-relative/stable ID or safe legacy migration | move-root media tests |
| SSE, pipeline state, checkpoint, actions | Slices 8 and 11 | backend-authoritative + broadcast/replay contract | two-subscriber/reconnect/action tests |
| Capability/status claims | Slice 12 | live consumer + evidence, inactive, unavailable, or diagnostic-only | manifest check + UI test |
| Interactive UI affordances | Slice 13 | wired, disabled with reason, or removed | Testing Library + browser/keyboard check |
| Prompts and agent skills | Slice 14 | current routing/model guidance or historical-only | source comparison + doc check |
| Dependencies | Adapter slice + Slice 14 | bounded version proven by tests or deliberately retained | `pip check`, npm audit/build, adapter tests |
| Current product docs | Slices 1, 2, 12, 14 | semantically synchronized; generated fact blocks checked | `check_doc_claims.py` + smoke |
| Dead/refactor candidates | Slice 15 | retained with caller, deferred with pin, or removed with proof | grep/call graph + mutation/contract test |

## Provider and model currency ledger

“Current” below means the source call shape was compared with a primary
provider contract on 2026-07-30. It does not mean a model is empirically best
for this product. Provider-advertised ranking, quality, latency, and cost must
stay labeled as provider claims until a committed instrument and `logs/`
artifact measures the production workload.

### Video generation

| Product key/path | Checked contract | Audit status | Disposition / owner |
|---|---|---|---|
| `GEMINI_OMNI` / `gemini_omni_native.py` | [Gemini Omni](https://ai.google.dev/gemini-api/docs/omni) | Primary adapter writes base64 text as bytes, mishandles URI polling/download, omits failed terminal handling, and is excluded from portrait despite documented 9:16 | Repair in Slice 3; offline inline/URI/failure/portrait fixtures |
| `VEO_NATIVE` / `veo_native.py` | [Gemini video](https://ai.google.dev/gemini-api/docs/video) | Model IDs current; registry overstates extra-reference/driving-video behavior and runtime provider fallback is ambiguous | Correct provider selection and claims in Slices 2/6 |
| `VEO` FAL | [FAL Veo 3.1 reference-to-video](https://fal.ai/models/fal-ai/veo3.1/reference-to-video/api) | Current call shape | Retain; catalog/contract coherence test |
| `SEEDANCE` | [FAL Seedance 2.0 image-to-video](https://fal.ai/models/bytedance/seedance-2.0/image-to-video/api) | Current call shape | Retain; no forced migration |
| `KLING_3_0` | [FAL Kling v3 Pro image-to-video](https://fal.ai/models/fal-ai/kling-video/v3/pro/image-to-video/api) | Current call shape | Retain; no forced migration |
| `KLING_NATIVE` | no current public official contract established | Legacy `kling-v1-6` path | Mark legacy/unverified; do not present as preferred |
| `LTX` native/FAL | [LTX models](https://docs.ltx.io/models), [I2V request](https://docs.ltx.io/api-documentation/api-reference/video-generation/image-to-video) | Native selects `ltx-2-3-pro` but defaults to invalid 4 seconds, omits silent-audio intent, and does not safely fall back on contract failure; Fast 1080p/24–25 supports longer durations while Pro supports 6/8/10 | Repair in Slice 4; deliberately restrict the selected Pro product profile to 6/8/10 and model the full matrix truthfully |
| `SORA_2` FAL | [FAL endpoint](https://fal.ai/models/fal-ai/sora-2/image-to-video/api) | Provider marks endpoint deprecated and unsupported | Retire immediately in Slice 2 |
| `SORA_NATIVE` | [OpenAI model](https://developers.openai.com/api/docs/models/sora-2), [shutdown notice](https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation) | Deprecated; Videos API shutdown 2026-09-24 | Keep only as visibly deprecated, date-gated fallback until sunset; automatically disable after |
| `RUNWAY_GEN4` | [Runway models](https://docs.dev.runwayml.com/guides/models/) | Source calls `gen4_turbo` with one image while label says Gen-4/three references | Rename/correct in Slice 5; separately evaluate Gen-4.5/router in Slice 6 |
| legacy Runway FAL/Gen-3 | [Runway lifecycle/pricing](https://docs.dev.runwayml.com/guides/pricing/) | Legacy/deprecated path remains | Catalog as legacy/retire under Slice 2/5 |

### Image, LLM, and vision

| Product path | Checked contract | Audit status | Disposition / owner |
|---|---|---|---|
| FAL Flux Kontext Max Multi, Flux 1.1 Ultra, Schnell | direct primary endpoint links not yet recorded | Source calls appeared contract-compatible, but the durable ledger remains `unverified` until Slice 2 records each exact FAL model page; Kontext quality/cost positioning is experimental | Verify and retain with truthful maturity in Slice 2 |
| `gemini-2.5-flash-image` | [Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations) | Published shutdown 2026-10-02 | Evaluate/migrate to documented replacement under Slice 6 |
| Gemini 2.5 Pro/Flash text/vision | [Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations) | Published shutdown 2026-10-16 | Evaluate/migrate replacements under structured-output/vision fixtures in Slice 6 |
| GPT-4o across ensemble/decomposition/vision/research | [GPT-4o model](https://developers.openai.com/api/docs/models/gpt-4o), [latest-model guide](https://developers.openai.com/api/docs/guides/latest-model) | Repeated default; the alias remains listed while specific snapshots have separate lifecycle states | Evaluate exact configured IDs and a Responses/GPT-5.6 candidate in Slice 6; migrate only with lifecycle or measured product benefit, never by string replacement |
| Anthropic Messages, Sonnet 4.6 / Opus 4.8 | [POST `/v1/messages`](https://platform.claude.com/docs/en/api/messages/create) | Current source call shape; exact selected model lifecycle is rechecked in Slice 2 | Retain; no forced migration without a contract reason |
| planned HiDream/SD3.5 entries | no production dispatcher | Advertised/planned only | Non-dispatchable catalog entries; no UI production claim |

### Speech, music, performance, lip-sync, foley, and post

| Product path | Checked contract | Audit status | Disposition / owner |
|---|---|---|---|
| ElevenLabs `eleven_v3` TTS/dialogue | [POST `/v1/text-to-speech/:voice_id`](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [Eleven v3 capability page](https://elevenlabs.io/text-to-speech-api) | Current source calls; dedicated dialogue-mode endpoint/version still needs its exact Slice 2 ledger link | Retain; no forced SDK migration |
| Cartesia `/tts/bytes`, Sonic 2 | [Cartesia API changes](https://docs.cartesia.ai/build-with-cartesia/tts-models/api-changes) | Supported; version header is stale and Sonic 3.5 is a candidate | Correct header; evaluate 3.5 rather than blind upgrade in Slice 6 |
| `OPENAI_AUDIO` registry entry | scoped active-domain search shown above | Marked live while the scoped search found only a removed-function note and registry/ranking entries; full mechanical inventory remains required, so current status is `unverified/unwired` rather than a source-wide absence claim | Inventory task confirms; then mark planned/unwired or implement only after product decision |
| FAL Sync v3, MuseTalk, LatentSync, Sync v2, OmniHuman 1.5, Creatify Aurora | direct primary endpoint links not yet recorded | Source calls appeared contract-compatible, but each row remains `unverified` until Slice 2 records the exact FAL model page/version | Verify individually; retain only under catalog coherence tests |
| Runway `act_one` performance adapter | [Runway models](https://docs.dev.runwayml.com/guides/models/), [SDK mapping](https://docs.dev.runwayml.com/api-details/sdks/) | SDK supports `act_two`; current code sends unsupported model/duration and does not REST-fallback on SDK errors | Migrate in Slice 5 |
| Viggle `api.viggle.ai/v1` | no official contract established | Undocumented/unverified | Disable in Slice 6 until contractable |
| Suno music path | source/provider audit | Uses SunoAPI.org proxy, not an official Suno developer API | Rename truthfully and require explicit vendor/data-handling acceptance |
| Stable Audio FAL music | direct primary endpoint link not yet recorded | Live fallback while registry says planned; endpoint/model remains `unverified` in this durable ledger | Verify exact model, then correct catalog in Slice 6 |
| Stability Foley | [Stability API reference](https://platform.stability.ai/docs/api-reference) | Current endpoint; newer model variants are separate evaluation | Retain; evaluate only with measured benefit |
| PixVerse swap, RIFE, SeedVR2 | direct primary endpoint links not yet recorded | Source calls appeared contract-compatible and SeedVR2 audio restoration is present, but the ledger remains `unverified` until exact model pages/versions are recorded | Verify individually in Slice 2; no forced migration without evidence |

### Research and discovery

| Product path | Checked contract | Audit status | Disposition / owner |
|---|---|---|---|
| Firecrawl in `web_research.py` and `research_engine.py` | [Python quickstart](https://docs.firecrawl.dev/quickstarts/python) | Both callers use obsolete `scrape_url(..., params=...)` and dict access; installed SDK expects `scrape(..., formats=...)` and returns `Document` | One shared adapter in Slice 5 |
| Tavily | [Python SDK reference](https://docs.tavily.com/sdk/python/reference) | Current source call shape | Retain |
| Pexels | scoped active-domain search shown above | Only configuration/constant sites appeared in the scoped result; full mechanical inventory remains required, so production use is `unverified` | Inventory task confirms; then mark unused or retain with a real caller |

## UI ↔ backend contract ledger

| Surface | Verified mismatch | Production/read-write evidence | Disposition / verifier |
|---|---|---|---|
| Character LoRA | Paid training can start; validation structurally skips; skipped output can register; generation consumer is absent | `CharacterPanel.tsx`, `web_server.py:api_train_lora`, `prep/lora_quality.py`, `phase_c_assembly.py:generate_ai_broll` | Slice 1: deny all entry/registration paths, inactive UI/manifest, mutation tests |
| Engine/spend controls | Face-swap display default disagrees with runtime; hidden fallbacks can still spend | `VideoSection.tsx`, `cinema/shots/controller.py`, `phase_c_ffmpeg.py` | Slice 9: canonical defaults and reciprocal tests |
| Project selection/lifecycle | A→B keeps page/focus/stages/shots/failures/halt; runs are not hydrated; start/cancel ignore failure | `App.tsx`, `PageContext.tsx`, `usePipelineState.ts`, pipeline-state route | Slice 8: PID boundary, epoch guard, backend `running/allowed_actions`, typed errors |
| Media persistence | Absolute output paths break after repo move while root guard correctly returns 403 | shot controller publication, `/file`, `PreviewPanel.tsx` | Slice 10: relative/media IDs + safe legacy migration tests |
| Mutation error handling | Most mutations do not check non-2xx; 409 can close editors or paint optimistic success | character/settings/review/prompt components | Slices 8/9/13: typed boundary then feature migration |
| Settings writes | Whole stale `global_settings` snapshots race and clobber; inputs write on every change | `SettingsInspector.tsx`, controls, `api_update_project` | Slice 9: validated patch/revision or explicit Save |
| LTX control | UI has no duration; runtime supplies invalid native default; stored duration is ignored | `VideoSection.tsx`, `phase_c_ffmpeg.py`, `ltx_native.py` | Slice 4 + 9 contract |
| Voice/language | Forced-alignment display/default/consumer disagree; TTS provider/voices/lipsync priority stored but ignored; WPM copy says unwired though runtime consumes it; language does not apply tuned defaults | `VoiceSection.tsx`, `audio/dialogue.py`, language-default route | Slice 9: wire real consumers, remove decorative settings |
| SSE/progress | Subscribers compete for one queue; no replay IDs; backend stages drift from 14-stage rail | `web_server.py` event queues, `useSSE.ts`, `usePipelineState.ts` | Slice 11: fan-out/replay/stage contract |
| Target schema | Full multi-modality/planned registry is accepted as shot target; unknown dispatch silently cascades | scene schema, shot PUT, prompt optimizer, dispatcher | Slice 2: selectable video target boundary |
| Capability page | Raw IDs/hashes/internal notes, ArcFace label despite GhostFaceNet, retired max/LoRA claims | capability scorecard/manifest/UI | Slice 12 |
| Interactive semantics | Filmstrip/transport affordances inert; reorder mouse-only; modal focus/live errors incomplete | shared/edit/scene/UI primitives | Slice 13 |

### Operator API coverage still open

The final ledger must either surface or deliberately classify these current
backend operations:

- pipeline state, checkpoint, and explicit resume/new-run choice;
- language-default application;
- project rename/delete;
- cleanup, disk usage, and cleanup-all;
- location research and style-board upload;
- provider credential/readiness status;
- per-engine duration/resolution/native-audio controls;
- creative/quality-judge model, prompt optimizer, competitive generation, and
  auto-approve configuration.

Not every route belongs in the UI. “API-only” or “internal” is an acceptable
final disposition when the product rationale and tests are explicit.

## Documentation, prompt, capability, and dependency ledger

| Surface | Audit result | Owner / final verifier |
|---|---|---|
| `ARCHITECTURE.md` | Anchor check green but several semantic sections need current engine/state/capability truth | Touched alongside mechanism slices; final Slice 14 smoke/doc check |
| `README.md` | Semantically stale UI/gate/image-tier summary | Slice 14 |
| `OPERATIONS.md` | Retired max/PuLID setup and routing/environment claims | Slice 14 |
| `docs/PROGRAM-MANUAL.md` | 93 auto-fixable anchor drifts + 2 manual; semantic contradictions around routing/capability | Mechanism-specific edits, then controlled Slice 14 regeneration/check |
| `config/prompts/pipeline_context.md` | Native-audio, transition, and retired PuLID timing drift | Slice 14, backed by live routing |
| `.agents/skills/ai-video-gen/SKILL.md` | Shot-primary table is stale relative to current Gemini-first selector | Slice 14 after engine truth lands |
| `.agents/skills/comfyui-mastery/SKILL.md` | Governs ComfyUI graph work; no current graph rewrite authorized | Retain unless a later owned graph task fires |
| `.env.example` | Dead/misleading keys and precedence/default drift | Slice 14 from environment schema |
| `docs/pipeline_status.toml` / capability UI | Syntactic anchors allow false semantic “wired” claims | Slices 1/12 |
| Python requirements | Broad minimums; installed provider SDKs have available updates; `pip check` clean | Adapter-by-adapter constraints only; no blanket upgrade |
| `requirements-lock-py39.txt` | Historical snapshot differs from current venv | Preserve as labeled history or create a new current lock |
| npm dependencies | Production audit reported no vulnerabilities; outdated packages include majors | Update only for owned UI need, then test/build |

## Refactor/deletion candidates — deferred until contracts are green

| Candidate | Current evidence | Required disposition |
|---|---|---|
| `cinema/pipeline.py:CinemaPipeline` | RESOLVED — deleted 2026-08-01 (ADR-081); zero callers re-verified at full scope with a literal (non-regex) pattern | none |
| `ltx_native.py` transition helpers | candidate only; full-scope absence not yet evidenced | Re-evaluate after LTX contract repair |
| `face_validator_gate.py` helper methods | candidate only; full-scope absence not yet evidenced | Preserve until identity slice proves deletion safe |
| `cinema/auto_approve.py:summarize_audit` | candidate only; full-scope absence not yet evidenced | Remove only under Slice 15 |
| Root package manifest/lock | candidate only; external tooling role unverified | Check external tooling before deletion |
| Large video/keyframe dispatch functions | high fan-out and billing/cascade semantics | Extract provider attempts only under contract/mutation tests |
| Root domain import shims | candidate set only; exact live-caller inventory not yet recorded here | Inventory callers, migrate imports first, and do not mass-delete |

## Initial execution ledger

`BASE` is refreshed immediately before each worker dispatch; `decf72ee` is only
the audit baseline.

| Slice/task | Owned files (exact brief required before dispatch) | Dependency | Implementer/reviews | State |
|---|---|---|---|---|
| 0.1 mechanical surface inventory | `scripts/product_surface_inventory.py`, its test, generated active-surface artifact/check mode | plan commit; may follow urgent spend containment | fresh worker → spec reviewer → quality reviewer | LANDED (`ea59894c`…`7b8b6786`); post-fix re-review owed |
| 1a LoRA mechanism containment | `prep/lora_policy.py`, `prep/lora_quality.py`, `prep/lora_training.py`, `web_server.py`, three direct training/registration scripts, focused backend tests, appended ADR | plan commit | reserved worker `lora_containment_impl` → `lora_containment_spec` → `lora_containment_quality` | LANDED + reviewed GO (`411146aa`/`2e24346f`/`871c10f2`) |
| 1b LoRA product truth | character/identity/capability UI, pod-gating/type tests, capability scorecard/manifest, source comments, `ARCHITECTURE.md`, affected Program Manual sections | 1a GO | fresh UI/docs worker → independent spec reviewer → independent quality reviewer | LANDED + reviewed GO (`d686f2ca`/`7ac36338`) |
| 2a provider ledger + catalog types | checked-at modality ledger, typed static fields/runtime-availability projection, compatibility registry, coherence tests | Slice 1 for spend policy | fresh worker → two independent reviewers | LANDED + reviewed GO (`cf25eee3` + fixes) |
| 2b routing/schema/dispatch boundary | scene schema/validator, optimizer coercion, rankings/cascade, dispatcher fail-fast, cost/caller tests | 2a | fresh worker → two independent reviewers | LANDED backend (`8fc46759` family); reviews owed; see plan ledger |
| 2c config + all UI selectors | `/api/config`, `web/src/lib/engines.ts`, ScenePanel/ShotRow/PromptEditor/inspector selectors and tests | 2a/2b | fresh UI worker → two independent reviewers | OPEN |
| 3 Gemini Omni | Gemini adapter, portrait declaration, focused tests/dependency constraint | Slice 2 catalog fields | fresh worker → two reviewers | LANDED (`caad6bcf`, repaired + re-admitted; reviewed) |
| 4 LTX | LTX adapter/dispatcher/config, safe download, focused tests | Slice 2 parameter contract | fresh worker → two reviewers | OPEN |
| 5a Firecrawl | shared Firecrawl adapter, `web_research.py`, `research_engine.py`, dependency constraint and focused tests | Slice 2 lifecycle truth | fresh worker → two independent reviewers | LANDED (`c8327b34` family); reviews owed |
| 5b Runway performance | `performance/act_one.py` migration/rename, registry/labels, SDK/REST polling tests | Slice 2 lifecycle truth | fresh worker → two independent reviewers | OPEN |
| 6a OpenAI LLM decision | exact configured IDs, one candidate Responses adapter, structured/tool/vision/cost evaluation artifacts | checked provider ledger | fresh worker → two independent reviewers | OPEN |
| 6b Gemini image/text/vision | model IDs, media/structured-output fixtures, bounded SDK constraint | 2a and 3 | fresh worker → two independent reviewers | OPEN |
| 6c1 Cartesia | dialogue adapter/header/model decision, focused behavior/contract tests | 2a | fresh worker → two independent reviewers | OPEN |
| 6c2 music/foley | Stable Audio + Suno proxy truth/evaluation, one provider per commit if production code changes | 2a | sequential fresh workers → two reviews each | OPEN |
| 6c3 unverified integrations | OpenAI Audio, Viggle, and Pexels inventory/status guards; split implementation from pure catalog correction | 0.1 and 2a | sequential fresh workers → two reviews each | OPEN |
| 7 continuity/identity | continuity engine, optimizer merge, controller call path, tests | provider repairs independent | fresh worker → two reviewers | OPEN |
| 8 project/action authority | pipeline-state route, typed API client, App/hook/shell/run controls/tests | basic server contract | fresh worker → two reviewers | OPEN |
| 9a settings write contract | project mutation PATCH/revision or explicit-save API, schema/conflict tests | Slices 2, 8 | fresh backend worker → two reviewers | OPEN |
| 9b video/spend settings | video inspector, engine duration/audio, face-swap/cascade defaults and runtime readers/tests | 9a and Slice 2 | fresh worker → two reviewers | OPEN |
| 9c voice/language settings | voice inspector, TTS/default-voice/lipsync/WPM/language-default consumers and tests | 9a | fresh worker → two reviewers | OPEN |
| 9d identity/object stored settings | `ip_adapter_weight`, `scale_reference`, and other unconsumed fields: wire or remove with tests | 9a | one focused worker per consumer family → two reviews | LANDED in two steps: `6e7477a0` labeled all three read-only; the `ip_adapter_weight` REMOVE decision then deleted it end to end (UI/API/factories/`characters.json`) + retired the now-impossible `confirmed[15]` validation pins. `scale_reference` remains read-only pending its `llm/prompt_optimizer.py` wiring. |
| 10 media portability | publishers, path model, file route, previews/tests | project boundary | fresh worker → two reviewers | OPEN |
| 11a event fan-out/replay | backend subscriber registry, monotonic IDs, snapshot/replay contract and concurrency tests | Slice 8 | fresh backend worker → two reviewers | OPEN |
| 11b stage/reconnect reducer | canonical event vocabulary, UI reducer/reconnect state/tests | 11a | fresh UI worker → two reviewers | OPEN |
| 11c checkpoint/resume/review actions | explicit resume/new-run and advanced allowed-action transitions/tests | 11a/11b | fresh worker → two reviewers | OPEN |
| 12 capability | manifest/scorecard/readiness, operator UI/tests | Slices 1, 2, provider decisions | fresh worker → two reviewers | OPEN |
| 13a shared UX/a11y contract | feedback/dialog/focus/live-region primitives and automated a11y harness | Slices 8–12 | fresh UI worker → two reviewers | OPEN |
| 13b Setup polish | Setup page/tree/cue/settings density, empty/error/busy states and tests | 9, 12, 13a | fresh UI worker → two reviewers | OPEN |
| 13c Edit/Run polish | media/timeline/filmstrip/run controls/states and tests | 8, 10, 11, 13a | fresh UI worker → two reviewers | OPEN |
| 13d Capability + no-spend E2E evidence | Capability hierarchy, real-server seeded journey, named screenshots/a11y logs | 12, 13a–c | fresh UI/E2E worker → two reviewers | OPEN |
| 14a prompts/env/skills/generated facts | `pipeline_context`, environment schema/example, active skills, generated/check mode | mechanism slices green | doc/config worker → two reviewers | OPEN |
| 14b operator docs | `README.md`, `ARCHITECTURE.md`, `OPERATIONS.md`, relevant status/config references | 14a + mechanism slices | doc-sync worker → two reviewers | OPEN |
| 14c Program Manual + final drift gate | affected manual sections, anchor corrections, final doc/smoke/dependency matrix | 14a/14b | manual worker → two reviewers | OPEN |
| 15a `CinemaPipeline` candidate | `cinema/pipeline.py` | deleted; suite + smoke green | director decision (ADR-081) | DONE |
| 15b LTX transition helpers | DELETED 2026-08-01 (ADR-083) — private methods with no caller even inside their own module; no public transition entry point; transitions ship via ffmpeg `xfade_concat` (`cinema_pipeline.py:1487`). Removed with 2 transitively-orphaned helpers; `_upload_to_fal`/`_fal_duration`/`NATIVE_BASE_URL` KEPT (live callers) | Slice 4 + full matrix | director decision (ADR-083) | DONE |
| 15c face-validator helpers | UPDATED 2026-08-05 — `face_validator_gate.score_candidate` remains imported by `prep/lora_quality.py:202`, behind the unconditional dormant-LoRA policy. The three unreferenced manual pod/spend probes that also imported it were removed. A per-function `git grep -c ... \| wc -l` sweep had reported all helpers unreferenced; that was a HARNESS ARTIFACT (`-c` prints one line per file), so the helper itself remains until the dormant LoRA implementation is retired as a unit. | Slice 7 + full matrix | — | CLOSED — manual probes deleted; guarded helper retained |
| 15d `summarize_audit` | CLOSED 2026-08-01 — already decided, not pending evidence: `DECISIONS.md` records `auto_approve.summarize_audit` as explicitly KEPT by the user in the 2026-06-03 prune cycle (`cinema/auto_approve.py:777`, tested at `tests/unit/test_auto_approve.py:448`) | full matrix | — | CLOSED — user-kept |
| 15e root package manifests | root manifests plus external-tooling inventory | task 0.1 | fresh worker → two reviewers | BLOCKED ON EVIDENCE |
| 15f dispatcher extraction | one provider attempt per task with billing/cascade/aspect mutation tests | provider slices green | fresh worker → two reviewers | BLOCKED ON EVIDENCE |
| 15g domain shims | one shim/import family per task after caller migration | task 0.1 + full matrix | fresh worker → two reviewers | BLOCKED ON EVIDENCE |

### Next dispatch record — Task 1a

- **BASE:** the plan/audit commit produced from these two documents; the root
  orchestrator passes its exact SHA in the worker prompt after the commit
  succeeds.
- **Implementer:** reserved task name `lora_containment_impl`.
- **Exact owned production/docs pathspec:**
  `prep/lora_policy.py`, `prep/lora_quality.py`, `prep/lora_training.py`,
  `web_server.py`, `scripts/_fal_lora_train.py`,
  `scripts/_fal_man_lora_train.py`, `scripts/_register_aria_lora.py`, and an
  appended entry in `DECISIONS.md`.
- **Exact owned test pathspec:**
  `tests/unit/test_web_server_train_lora_gated.py`,
  `tests/unit/test_lora_quality.py`,
  `tests/unit/test_lora_training_singletrain.py`,
  `tests/unit/test_lora_dormant_containment.py`, and replacement of the stale
  `tests/unit/test_has_character_lora_only_hole.py` pin.
- **Real callers/writes:** web POST → gated trainer → raw trainer/subprocess;
  two direct FAL scripts; direct registration script; generic project PUT
  writes to `char_lora_paths`, `char_lora_strengths`, and
  `char_lora_triggers`.
- **Verification:** focused files above plus
  `tests/unit/test_project_persistence.py`, mutation bombs for thread,
  subprocess, upload/subscription, and registry writes,
  `scripts/ci_smoke.py`, and `git diff --check`.
- **Spec reviewer:** reserved `lora_containment_spec`; verdict pending actual
  `BASE..HEAD`.
- **Quality reviewer:** reserved `lora_containment_quality`; starts only after
  spec GO; verdict pending.
- **Disposition:** CLOSED (historical). Landed as `411146aa` with fixes
  `2e24346f`/`871c10f2`; independent spec GO and Lane V quality GO recorded
  in the plan ledger. Task 1b landed subsequently (`d686f2ca`/`7ac36338`).

## Browser observations to reproduce after changes

The current built product was inspected through the real local Flask server:

- Setup is dense and low-contrast, with large unused center space.
- Edit/Run can show blank or broken media without an explanatory state.
- Run shows active/cancel/review affordances while the backend snapshot is idle.
- Capability exposes raw engine IDs, hashes, internal notes, retired max/LoRA
  claims, and stale ArcFace labeling.
- Voice copy says WPM is not wired although production consumes it.
- No browser console errors were observed in the baseline walkthrough.

Final evidence must retain the named states at both `1440x1000` and `1024x768`
under `logs/ui/product-unification/<viewport>/`, plus
`logs/ui/product-unification/a11y.txt`. The seeded no-spend journey must record
its command/output in `logs/ui/product-unification/e2e.txt`. Slice 13 introduces
or documents the reproducible screenshot command and
`npm --prefix web run test:a11y`; project selection, Setup, Edit, Run,
Capability, loading, empty, idle, running, error, and resumed states are all
required.
