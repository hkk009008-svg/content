"""Offline tests for the LoRA quality gate (no GPU/ComfyUI — all boundaries mocked)."""
import pytest
from prep.lora_quality import _next_lora_action, LoraAction

THRESH, BASE, BUDGET = 0.6, 0.45, 3


@pytest.mark.parametrize("attempt,score,expected", [
    (0, 0.72, LoraAction.ACCEPT),            # meets threshold on first train
    (0, None, LoraAction.ACCEPT),            # validation skipped -> accept (register unvalidated)
    (0, 0.50, LoraAction.RETRY_MORE_STEPS),  # 1st low score -> escalate steps
    (1, 0.55, LoraAction.RETRY_HIGHER_RANK), # 2nd low score -> escalate rank
    (2, 0.50, LoraAction.ACCEPT),            # budget exhausted, best >= baseline -> keep best
    (2, 0.40, LoraAction.REJECT),            # budget exhausted, best < baseline -> reject (PuLID-only)
    (2, 0.60, LoraAction.ACCEPT),            # exactly at threshold on final -> accept
])
def test_next_lora_action(attempt, score, expected):
    assert _next_lora_action(attempt, score, threshold=THRESH, baseline=BASE, budget=BUDGET) is expected
