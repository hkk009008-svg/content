"""MAX_QUALITY_TEMPLATES halt_rule pins (operator Lane V 01:30:23Z latent-gap
disposition, 2026-06-11).

Before this, NO template carried halt_rule — quality_max.py:1070 fell back to
"composite_only" everywhere, leaving every template's halt_threshold_arc DEAD
(arc is informational under composite_only) unless the max_halt_rule UI knob
was set. Director disposition: per-shot-class explicit defaults — conjunctive
where faces dominate the frame and arc is reliable (portrait, medium),
composite_only where arc is unreliable or absent (action: motion blur; wide:
distant faces; landscape: no identity stack at all). The regenerate_floor_arc
backstop is independent of halting and stays for all classes.
"""
from workflow_selector import MAX_QUALITY_TEMPLATES, get_max_quality_params


def test_every_template_declares_halt_rule_explicitly():
    for name, tpl in MAX_QUALITY_TEMPLATES.items():
        assert "halt_rule" in tpl, f"{name} template silently inherits the fallback"


def test_face_dominant_classes_halt_conjunctively():
    assert MAX_QUALITY_TEMPLATES["portrait"]["halt_rule"] == "conjunctive"
    assert MAX_QUALITY_TEMPLATES["medium"]["halt_rule"] == "conjunctive"


def test_arc_unreliable_classes_halt_on_composite_only():
    for name in ("action", "wide", "landscape"):
        assert MAX_QUALITY_TEMPLATES[name]["halt_rule"] == "composite_only", name


def test_conjunctive_classes_carry_live_arc_thresholds():
    # the halt_threshold_arc values these classes carry must be real gates
    # (>0) now that the rule reads them
    for name in ("portrait", "medium"):
        assert MAX_QUALITY_TEMPLATES[name]["halt_threshold_arc"] > 0, name


def test_get_params_propagates_halt_rule():
    assert get_max_quality_params("portrait")["halt_rule"] == "conjunctive"
    assert get_max_quality_params("landscape")["halt_rule"] == "composite_only"
