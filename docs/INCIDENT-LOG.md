# Incident Log — Post-emergency reviews (Protocol Bundle v5 §E)

**Established:** Protocol Bundle v5 (ship at this commit), per the
emergency-handling protocol.

This log captures post-incident reviews for v5 §E emergencies —
events that triggered the temporary-authority carve-out from normal
role partition. Each entry documents what happened, what was done,
which protocol gap (if any) allowed the emergency, and what (if
anything) should be codified to prevent recurrence.

**Scope reminder (v5 §E criteria):**

1. Production-affecting OR user-data-integrity issue
2. Security-critical (active-exploit CVE / secrets leak)
3. Active bleed-rate (cost / resource / token burn per minute)
4. External time-pressure (deadline at risk)

Events outside these criteria are NOT emergencies; they use normal
role partition + proposal cycle, even if urgent-feeling.

---

## Entry template

```markdown
## INC-NNN — <short title> (YYYY-MM-DD)

**Trigger category:** <1-4 from v5 §E scope>
**First-noticer seat:** director-seat / operator-seat
**Responding seat:** director-seat / operator-seat (note if
  temporary-authority carve-out was invoked)
**Stop-the-bleed action SHA:** `<sha>`
**Time-to-mitigation:** <minutes>

### What happened
<one-paragraph description of the event>

### Mitigation
<one-paragraph description of stop-the-bleed action>

### Root cause (if known)
<one-paragraph; "TBD post-incident analysis" if not yet known>

### Protocol gap (if any)
<what allowed this emergency to occur; was current protocol silent
on prevention?>

### Codification proposal (if any)
<rule / lane / scope change candidate for next bundle's REPLY cycle>
```

---

## Active entries

_(Empty at v5 ship. First incident will be filed here when it
occurs.)_

---

## Closed entries

_(None yet.)_
