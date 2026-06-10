def test_ci_red_proof():
    """Intentional failure - proves the CI pytest job goes RED on a broken branch (P0-1 acceptance). Never merge."""
    assert False, "intentional red for CI acceptance"
