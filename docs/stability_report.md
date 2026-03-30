# GitNexus Stability Report

## Purpose

This document defines a repeatable GitNexus-based stability score for the `Content`
repo. It measures structural change risk, not runtime uptime or production health.

Use it to answer:

- How risky is the current codebase to change?
- How isolated is the current diff?
- Which shared hubs make the system fragile?

## What GitNexus Can Measure

GitNexus is useful for measuring:

- blast radius of a symbol change
- execution-flow spread
- shared utility and hub concentration
- whether current edits spill into unexpected processes

GitNexus does not directly measure:

- crash rate
- latency
- memory leaks
- production error frequency
- flaky infra or third-party outages

## Score Model

### 1. Baseline Stability Score

Score range: `0-100`

```text
Baseline Stability Score
= Structural Headroom (35)
+ Change Safety (45)
+ Blast-Radius Isolation (20)
```

#### Structural Headroom (35)

Use repo-wide graph density as the structural penalty.

```text
symbols_per_file   = symbols / files
edges_per_symbol   = edges / symbols
processes_per_file = processes / files

Structural Headroom
= 35 * (1 - avg(
    clamp((symbols_per_file - 6) / 12, 0, 1),
    clamp((edges_per_symbol - 3) / 4, 0, 1),
    clamp((processes_per_file - 0.4) / 0.8, 0, 1)
  ))
```

Interpretation:

- more symbols per file means denser files
- more edges per symbol means tighter coupling
- more processes per file means more cross-cutting behavior

#### Change Safety (45)

Use `gitnexus_detect_changes()` to score the current working diff.

```text
risk_level score:
  low      = 20
  medium   = 12
  high     = 6
  critical = 0

process score
= 15 * (1 - clamp(affected_processes / 10, 0, 1))

file spread score
= 5 * (1 - clamp(changed_files / 10, 0, 1))

symbol spread score
= 5 * (1 - clamp(changed_symbols / 50, 0, 1))

Change Safety
= risk_level score + process score + file spread score + symbol spread score
```

#### Blast-Radius Isolation (20)

This is a direct reward for a diff that does not fan out into execution flows.

```text
Blast-Radius Isolation
= 20 * (1 - clamp(affected_count / 20, 0, 1))
```

### 2. Hotspot-Adjusted Stability Score

The baseline score can look healthy even when the repo has a few critical shared
hubs. The stronger version subtracts a hotspot fragility penalty.

```text
Hotspot-Adjusted Stability Score
= Baseline Stability Score - Hotspot Fragility Penalty
```

Penalty range: `0-25`

For each hotspot symbol:

```text
hotspot_pressure
= avg(
    clamp(direct_callers / 25, 0, 1),
    clamp(processes_affected / 15, 0, 1),
    clamp(modules_affected / 15, 0, 1),
    risk_weight
  )

risk_weight:
  low      = 0.25
  medium   = 0.50
  high     = 0.75
  critical = 1.00

Hotspot Fragility Penalty
= 25 * avg(hotspot_pressure across chosen hotspots)
```

Recommended hotspot set:

- top 5 shared functions by incoming calls or obvious centrality
- plus 1 change-adjacent hotspot if the current diff touches a core subsystem

## Current Snapshot

Date: `2026-03-29`

Repo stats from GitNexus:

- files: `88`
- symbols: `987`
- edges: `4565`
- processes: `72`

Current diff from `gitnexus_detect_changes({scope: "all"})`:

- changed symbols: `20`
- changed files: `2`
- affected processes: `0`
- risk level: `low`

### Baseline Score Calculation

```text
symbols_per_file   = 987 / 88  = 11.22
edges_per_symbol   = 4565 / 987 = 4.63
processes_per_file = 72 / 88   = 0.82

Structural Headroom
= 35 * (1 - avg(0.435, 0.408, 0.523))
= 19.1

Change Safety
= 20
+ 15 * (1 - 0/10)
+ 5 * (1 - 2/10)
+ 5 * (1 - 20/50)
= 42.0

Blast-Radius Isolation
= 20 * (1 - 0/20)
= 20.0

Baseline Stability Score
= 19.1 + 42.0 + 20.0
= 81.1
```

Baseline result: `81/100`

Interpretation: the codebase is structurally nontrivial, but the current working
diff is well-contained and low-risk.

### Hotspot Impact Scan

Hotspots selected for the stronger model:

| Symbol | File | Risk | Direct | Processes | Modules |
| --- | --- | --- | ---: | ---: | ---: |
| `_project_dir` | `project_manager.py` | `CRITICAL` | 9 | 18 | 19 |
| `save_project` | `project_manager.py` | `CRITICAL` | 21 | 15 | 13 |
| `load_project` | `project_manager.py` | `CRITICAL` | 24 | 15 | 13 |
| `get_project_dir` | `project_manager.py` | `CRITICAL` | 13 | 6 | 9 |
| `generate_ai_video` | `phase_c_ffmpeg.py` | `CRITICAL` | 6 | 4 | 6 |
| `_connect` | `quality_tracker.py` | `HIGH` | 7 | 2 | 4 |

Observations:

- `project_manager.py` is the primary fragility center
- `_project_dir`, `load_project`, and `save_project` are system-wide shared hubs
- `generate_ai_video` is a smaller but still critical pipeline dependency
- `_connect` is change-adjacent to the current diff, so it matters even though its
  spread is lower than the project-management hubs

### Hotspot-Adjusted Score Calculation

```text
hotspot_pressure(_project_dir)      = avg(0.36, 1.00, 1.00, 1.00) = 0.8400
hotspot_pressure(save_project)      = avg(0.84, 1.00, 0.87, 1.00) = 0.9267
hotspot_pressure(load_project)      = avg(0.96, 1.00, 0.87, 1.00) = 0.9567
hotspot_pressure(get_project_dir)   = avg(0.52, 0.40, 0.60, 1.00) = 0.6300
hotspot_pressure(generate_ai_video) = avg(0.24, 0.27, 0.40, 1.00) = 0.4767
hotspot_pressure(_connect)          = avg(0.28, 0.13, 0.27, 0.75) = 0.3575

Hotspot Fragility Penalty
= 25 * avg(0.8400, 0.9267, 0.9567, 0.6300, 0.4767, 0.3575)
= 17.4

Hotspot-Adjusted Stability Score
= 81.1 - 17.4
= 63.7
```

Hotspot-adjusted result: `64/100`

Interpretation: the current edits are safe, but the repo still has several shared
critical hubs that reduce whole-system change stability.

## How To Recompute

1. Ensure the index is current.

```bash
npx gitnexus status
```

If stale:

```bash
npx gitnexus analyze
```

2. Pull repo stats from GitNexus:

- `files`
- `symbols`
- `edges`
- `processes`

3. Run diff impact:

- `gitnexus_detect_changes({scope: "all"})`

4. Choose hotspot symbols:

- start with central shared functions
- include one diff-adjacent hotspot if the current work touches a core area

5. Run hotspot impact scans:

- `gitnexus_impact({target: "<symbol>", direction: "upstream"})`

6. Recompute:

- `Baseline Stability Score`
- `Hotspot Fragility Penalty`
- `Hotspot-Adjusted Stability Score`

## Reading The Numbers

- `80-100`: stable to change, low current spillover
- `60-79`: workable, but shared hubs or coupling need care
- `40-59`: fragile, regressions likely without strong tests
- `<40`: very unstable to change

For this repo right now:

- baseline score: `81/100`
- hotspot-adjusted score: `64/100`

That means the current diff is safe, but the system has several critical hub
functions that should be treated carefully and ideally covered by stronger tests,
wrappers, or further modularization.
