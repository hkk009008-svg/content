"""
VG-B1 closure tests — voice gender + language awareness in assign_voice.

Tier B Korean dialogue probe (2026-05-27 cycle-16) surfaced that
audio/dialogue.py's empty-voice fallback hardcoded ElevenLabs Adam (English
male) for ANY character with empty voice_id — including a Korean female
character. Root cause:

  1. domain/character_manager.assign_voice() picked VOICE_POOL[0] (Rachel
     English) when no preference was given; this was language-blind +
     gender-blind.
  2. audio/dialogue.py:354 dispatcher fallback hardcoded Adam English-male
     as the unconditional last resort.

VG-B1 fix:

  * assign_voice() accepts ``language`` and ``gender`` keyword params; both
    narrow VOICE_POOL by category before picking.
  * audio/dialogue.py fallback consults domain.language_defaults for a
    language-aware default_male_voice / default_female_voice (Korean
    female → 안나 Anna; Korean male → 준호 Junho).
  * Character schema gains optional ``gender`` field (extra="allow" already
    permitted the attribute; this codifies it on the Pydantic model +
    factory).

These tests pin the new behavior so a future regression that revives the
Rachel-or-Adam-everywhere fallback fails loudly.
"""

import pytest

from domain.character_manager import assign_voice, VOICE_POOL


def _empty_project(pid: str = "test_project") -> dict:
    """Minimal valid Project dict for assign_voice (Pydantic validation needs id)."""
    return {
        "id": pid,
        "characters": [],
        "locations": [],
        "scenes": [],
        "objects": [],
    }


def _voice_meta(voice_id: str) -> dict:
    """Look up VOICE_POOL entry by id."""
    return next(v for v in VOICE_POOL if v["id"] == voice_id)


class TestAssignVoiceLanguageGender:
    """Direct language+gender combinations from VOICE_POOL categories."""

    def test_korean_female_picks_first_korean_woman(self):
        """Korean female → 안나 (Anna), the first korean_woman entry."""
        proj = _empty_project()
        v = assign_voice(proj, language="Korean", gender="female")
        meta = _voice_meta(v)
        assert meta["category"] == "korean_woman"
        assert meta["name"].startswith("안나")  # 안나 (Anna)

    def test_korean_male_picks_first_korean_man(self):
        """Korean male → 준호 (Junho), the first korean_man entry."""
        proj = _empty_project()
        v = assign_voice(proj, language="Korean", gender="male")
        meta = _voice_meta(v)
        assert meta["category"] == "korean_man"
        assert meta["name"].startswith("준호")  # 준호 (Junho)

    def test_english_female_picks_first_woman(self):
        """English female → Rachel, the first woman entry."""
        proj = _empty_project()
        v = assign_voice(proj, language="English", gender="female")
        meta = _voice_meta(v)
        assert meta["category"] in {"woman", "young"}
        assert meta["name"] == "Rachel"

    def test_english_male_picks_first_man(self):
        """English male → Adam, the first man entry."""
        proj = _empty_project()
        v = assign_voice(proj, language="English", gender="male")
        meta = _voice_meta(v)
        assert meta["category"] == "man"
        assert meta["name"] == "Adam"


class TestAssignVoiceLanguageOnly:
    """Language hint without gender → narrow by voice_pool_filter only."""

    def test_korean_no_gender_picks_first_korean(self):
        """Korean filter narrows to korean_woman + korean_man categories;
        first in VOICE_POOL order is 안나 (Anna). This is the Min-ji case —
        cycle-16 Tier B project created Min-ji with empty gender + empty
        voice_id; pre-fix, dispatcher hit Adam (English male). Post-fix,
        language-aware path lands on Anna (Korean female).
        """
        proj = _empty_project()
        v = assign_voice(proj, language="Korean")
        meta = _voice_meta(v)
        assert meta["category"].startswith("korean_")

    def test_unknown_language_falls_through_default(self):
        """Unknown language → _default filter (None) → full VOICE_POOL → first."""
        proj = _empty_project()
        v = assign_voice(proj, language="Klingon")
        meta = _voice_meta(v)
        # _default voice_pool_filter is None → no filter → first in pool = Rachel
        assert meta["name"] == "Rachel"


class TestAssignVoiceGenderOnly:
    """Gender hint without language → narrow by category prefix."""

    def test_gender_female_picks_first_woman_category(self):
        proj = _empty_project()
        v = assign_voice(proj, gender="female")
        meta = _voice_meta(v)
        assert meta["category"] in {"woman", "korean_woman", "young", "child"}

    def test_gender_male_picks_first_man_category(self):
        proj = _empty_project()
        v = assign_voice(proj, gender="male")
        meta = _voice_meta(v)
        assert meta["category"] in {"man", "korean_man", "elderly"}


class TestAssignVoiceNoHints:
    """No language + no gender → legacy first-unused behavior preserved."""

    def test_no_hints_picks_first_unused(self):
        """Backward-compat — VG-B1 fix must not regress callers that pass no hints."""
        proj = _empty_project()
        v = assign_voice(proj)
        meta = _voice_meta(v)
        assert meta["name"] == "Rachel"  # VOICE_POOL[0]


class TestAssignVoiceAvoidDuplicates:
    """Filtered candidate pool still respects _get_used_voices."""

    def test_korean_female_skips_used_anna(self):
        """If 안나 (Anna) already assigned, picker advances to next korean_woman."""
        proj = _empty_project()
        proj["characters"] = [{
            "id": "char_existing",
            "name": "Existing",
            "voice_id": "uyVNoMrnUku1dZyVEXwD",  # 안나 (Anna)
        }]
        v = assign_voice(proj, language="Korean", gender="female")
        assert v != "uyVNoMrnUku1dZyVEXwD"
        meta = _voice_meta(v)
        assert meta["category"] == "korean_woman"
        # Next korean_woman is 지영 (Jiyoung)
        assert meta["name"].startswith("지영")

    def test_all_filtered_used_cycles_to_first(self):
        """When every voice in the filtered set is used, picker returns the
        first in the filtered set (cycle behavior, no infinite loop)."""
        proj = _empty_project()
        # Mark all 3 korean_woman voices as used
        used_ids = [v["id"] for v in VOICE_POOL if v.get("category") == "korean_woman"]
        proj["characters"] = [
            {"id": f"c{i}", "name": f"C{i}", "voice_id": vid}
            for i, vid in enumerate(used_ids)
        ]
        v = assign_voice(proj, language="Korean", gender="female")
        # All used → returns first in filtered set
        meta = _voice_meta(v)
        assert meta["category"] == "korean_woman"


class TestAssignVoicePreferenceWins:
    """Direct ``preference`` argument still wins over language/gender filter."""

    def test_preference_name_substring_overrides_filter(self):
        proj = _empty_project()
        # Asking for "Adam" while hinting Korean+female → should still return Adam
        v = assign_voice(proj, preference="Adam", language="Korean", gender="female")
        meta = _voice_meta(v)
        assert meta["name"] == "Adam"

    def test_preference_voice_id_overrides_filter(self):
        proj = _empty_project()
        anna_id = "uyVNoMrnUku1dZyVEXwD"
        v = assign_voice(proj, preference=anna_id, language="English", gender="male")
        assert v == anna_id


class TestCharacterFactoryGenderField:
    """make_character + Character Pydantic model both expose ``gender``."""

    def test_make_character_accepts_gender(self):
        from domain.project_manager import make_character
        ch = make_character("Min-ji", "Korean protagonist", gender="female")
        assert ch["gender"] == "female"

    def test_make_character_gender_defaults_empty(self):
        from domain.project_manager import make_character
        ch = make_character("Anonymous", "Unspecified")
        assert ch["gender"] == ""

    def test_pydantic_character_accepts_gender(self):
        from domain.models import Character
        c = Character(id="c1", name="Test", gender="male")
        assert c.gender == "male"

    def test_pydantic_character_gender_defaults_empty(self):
        from domain.models import Character
        c = Character(id="c1", name="Test")
        assert c.gender == ""


class TestVoiceAssignmentIntegrationVgB1:
    """End-to-end: the cycle-16 Tier B Min-ji failure mode no longer reproduces."""

    def test_korean_unspecified_gender_no_longer_picks_english_male(self):
        """Cycle-16 reproducer — Korean project, character with empty voice_id
        and empty gender (Min-ji's actual state at project-create time).
        Pre-fix: would hit dispatcher hardcoded Adam fallback. Post-fix:
        assign_voice + language-aware fallback both land on a Korean voice.
        """
        proj = _empty_project()
        v = assign_voice(proj, language="Korean")  # no gender specified
        meta = _voice_meta(v)
        assert meta["category"].startswith("korean_"), (
            f"VG-B1 regression — Korean project picked {meta['name']} "
            f"({meta['category']}); should land on korean_* category"
        )
        # Specifically should NOT be Adam (English male) — the user-reported
        # bug. Adam's voice_id is pNInz6obpgDQGcFmaJgB.
        assert v != "pNInz6obpgDQGcFmaJgB", (
            "VG-B1 regression — Korean project picked Adam (English male). "
            "This is the exact user-reported failure mode from cycle-16 Tier B."
        )
