# Handoff brief template

Copy, fill every slot, delete none. A slot you cannot fill truthfully is
UNKNOWN, written as UNKNOWN.

```
HANDOFF — <campaign> — <date>
FROM: <machine/session>   TO: <machine/session>

## Identity pins
repo SHA (this machine)   : <full 40-hex sha>   [cmd: git rev-parse HEAD]
package digest(s)         : <name> = <digest>   [cmd: python -B ... package_digest()]
transfer                  : https://github.com/<owner>/<repo>/archive/<full-sha>.zip
remote state (other side) : <what was last VERIFIED there, with command + output, or UNKNOWN>

## SUPERSEDED — do not act on these if encountered
- <stale digest/decision/instruction> -> superseded by <replacement>, <when/why>
- ...

## Verified state (command + output, host named)
- [<host>] <claim>
  $ <command>
  <real output>

## Blockers — with owner machine
- <blocker> — owner: <Mac|Windows|user>; unblocks when <condition>

## Next action per machine
- <machine>: <one imperative action>, then STOP and report.

## Constraints
- Do NOT <retry/patch/install/...>.
- <authority boundaries: what needs the user, what needs the other machine>
```
