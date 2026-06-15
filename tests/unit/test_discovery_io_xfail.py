"""Live regression for discovery-wf_13f9d2f6-f93, confirmed[8].

BUG: W2:MAJOR:download-urllib-notimeout
  phase_c_ffmpeg.py had seven video-download sites calling
  urllib.request.urlretrieve(url, path) with no timeout. A stalled CDN transfer
  could block the pipeline thread indefinitely. The fixed shape routes all seven
  provider branches through a local helper that calls performance._net.safe_download.

Source: logs/discovery-wf_13f9d2f6-f93.json confirmed[8]; refuters returned
  refuted=False (all seven bare call sites confirmed).
"""

import ast
import pathlib

_MODULE_PATH = pathlib.Path(__file__).parent.parent.parent / "phase_c_ffmpeg.py"
_EXPECTED_ENGINES = {
    "RUNWAY_GEN4",
    "SORA_2",
    "VEO",
    "KLING_3_0",
    "FAL_SVD",
    "RUNWAY",
    "SEEDANCE",
}

# ---------------------------------------------------------------------------
# Static source approach: the seven download branches are buried inside the
# large generate_ai_video() cascade. Building full API mocks for every engine is
# heavier than the row needs; AST checks still target the real production source
# and prove the non-vacuous fixed shape.
# ---------------------------------------------------------------------------


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def test_urlretrieve_download_sites_have_timeout_protection():
    """Assert every Phase-C video provider download is timeout-protected."""
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    raw_urlretrieve_calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            _dotted_name(node.func) == "urlretrieve"
            or (_dotted_name(node.func) or "").endswith(".urlretrieve")
        )
    ]
    assert raw_urlretrieve_calls == [], (
        "phase_c_ffmpeg.py must not use raw urlretrieve for provider video "
        f"downloads; found call(s) at {raw_urlretrieve_calls}."
    )

    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "performance._net"
        and any(alias.name == "safe_download" for alias in node.names)
        for node in tree.body
    ), (
        "phase_c_ffmpeg.py must import safe_download from performance._net, "
        "the shared timeout/size/scheme-checked download helper."
    )

    generate = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "generate_ai_video"
    )
    helper_defs = [
        node for node in generate.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_download_video_or_cascade"
    ]
    assert len(helper_defs) == 1
    helper = helper_defs[0]

    module_safe_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _dotted_name(node.func) == "safe_download"
    ]
    helper_safe_calls = [
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and _dotted_name(node.func) == "safe_download"
    ]
    assert len(module_safe_calls) == 1
    assert helper_safe_calls == module_safe_calls
    safe_call = helper_safe_calls[0]
    assert [arg.id for arg in safe_call.args[:2] if isinstance(arg, ast.Name)] == [
        "video_url",
        "output_mp4",
    ]

    guarded_calls = []
    for node in ast.walk(generate):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Call)
            and _dotted_name(node.test.operand.func) == "_download_video_or_cascade"
            and any(
                isinstance(stmt, ast.Return)
                and isinstance(stmt.value, ast.Call)
                and _dotted_name(stmt.value.func) == "try_next_api"
                for stmt in node.body
            )
        ):
            guarded_calls.append(node.test.operand)

    engines = {
        call.args[1].value
        for call in guarded_calls
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant)
    }
    assert len(guarded_calls) == 7
    assert engines == _EXPECTED_ENGINES
    assert {
        call.args[0].id
        for call in guarded_calls
        if call.args and isinstance(call.args[0], ast.Name)
    } <= {"video_url", "final_video_url"}
