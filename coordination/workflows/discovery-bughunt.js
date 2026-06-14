export const meta = {
  name: 'discovery-bughunt',
  description: 'Phase 0 adversarial bug-hunt across high-risk subsystems + refute pass',
  phases: [{ title: 'Find' }, { title: 'Refute' }],
}
const FINDING = {
  type: 'object', additionalProperties: false, required: ['findings'],
  properties: { findings: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    required: ['subsystem','file_line','fail_mode','reproducer','severity_guess'],
    properties: {
      subsystem:{type:'string'}, file_line:{type:'string'}, fail_mode:{type:'string'},
      reproducer:{type:'string'},
      severity_guess:{type:'string',enum:['CRITICAL','MAJOR','MEDIUM','MINOR']},
    }}}},
}
const VERDICT = { type:'object', additionalProperties:false, required:['refuted','reasoning'],
  properties:{ refuted:{type:'boolean'}, reasoning:{type:'string'} } }
const SUBSYSTEMS = [
  {key:'gates', probe:'auto_approve, face_validator_gate, motion_gate, identity_gate, coherence_analyzer'},
  {key:'money', probe:'core.py budget, cost-estimation, lip-sync pricing (unbounded-spend)'},
  {key:'io', probe:'image/video decode, API-error swallow, ffmpeg/ffprobe failure'},
  {key:'http', probe:'web_server.py destructive/state-mutating endpoints'},
  {key:'checkpoint', probe:'resume/checkpoint state reconstruction'},
  {key:'identity', probe:'PuLID/LoRA injection, secondary-char binding'},
]
const FIND = (s) => `Repo root /Users/hyungkoookkim/Content. READ-ONLY (grep/Read only). Hunt FAIL-OPEN bugs (not happy paths the tests already cover) in the ${s.key} subsystem: ${s.probe}. Focus on silent-degradation, NaN/inf, and swallowed-error paths. EXCLUDE the OpenCV determinism fix (PRE-CLOSED, ARCHITECTURE §11.1) and workflow_selector.py (closed by bf1034a). Each finding needs a concrete reproducer.`
const REFUTE = (f,i) => `Repo root /Users/hyungkoookkim/Content. READ-ONLY. A finder claims: ${f.subsystem} ${f.file_line} — "${f.fail_mode}" (repro: ${f.reproducer}). Try to REFUTE it — read the code + its guards/callers. Set \`refuted=true\` if you can PROVE it is NOT a real defect; set \`refuted=false\` only if you cannot disprove it after genuine effort. (Note the field direction: true = disproved, false = finding stands.) Skeptic #${i}.`

phase('Find')
const found = (await parallel(SUBSYSTEMS.map(s => () =>
  agent(FIND(s), {label:`find:${s.key}`, phase:'Find', schema:FINDING, model:'sonnet'}))))
  .filter(Boolean).flatMap(r => r.findings)

phase('Refute')
const judged = await parallel(found.map(f => () =>
  parallel([0,1].map(i => () =>
    agent(REFUTE(f,i), {label:`refute:${f.file_line}`, phase:'Refute', schema:VERDICT, model:'sonnet'})))
    .then(vs => { const ok = vs.filter(Boolean);
      // CONFIRMED requires BOTH refuters to have returned AND neither to refute.
      // (Guard the vacuous-truth: [].every() === true would confirm a finding whose
      //  refuters both died — the opposite of safe. A missing verdict => not confirmed.)
      return { finding:f, verdicts: ok, confirmed: ok.length === 2 && ok.every(v => !v.refuted) }; })))

return {  // refuter reasoning preserved in logs/discovery-<runid>.json (§3 finding-record)
  confirmed: judged.filter(j => j.confirmed).map(j => ({ ...j.finding, refuters: j.verdicts })),
  rejected:  judged.filter(j => !j.confirmed).map(j => ({ ...j.finding, refuters: j.verdicts })),
}
