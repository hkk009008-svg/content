"""AST pin: dormant LoRA arguments remain threaded but unconsumed."""

from __future__ import annotations

import ast
import inspect
import textwrap

import phase_c_assembly
from prep.lora_policy import LORA_POLICY


LORA_ARGUMENTS = {
    "char_lora_path",
    "char_lora_strength",
    "char_lora_trigger",
}


def _loaded_lora_arguments(source: str) -> set[str]:
    tree = ast.parse(textwrap.dedent(source))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "generate_ai_broll"
    )
    return {
        node.id
        for node in ast.walk(function)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id in LORA_ARGUMENTS
    }


def test_generate_ai_broll_does_not_consume_dormant_lora_arguments():
    assert LORA_POLICY == "dormant"
    signature = inspect.signature(phase_c_assembly.generate_ai_broll)
    assert LORA_ARGUMENTS <= set(signature.parameters)

    source = inspect.getsource(phase_c_assembly.generate_ai_broll)
    assert _loaded_lora_arguments(source) == set()


def test_ast_pin_detects_a_real_argument_load():
    synthetic_consumer = """
def generate_ai_broll(char_lora_path=None, char_lora_strength=None,
                      char_lora_trigger=None):
    return char_lora_path, char_lora_strength, char_lora_trigger
"""
    assert _loaded_lora_arguments(synthetic_consumer) == LORA_ARGUMENTS
