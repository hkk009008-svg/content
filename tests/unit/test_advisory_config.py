from cinema.auto_approve import AdvisoryConfig


def test_defaults():
    cfg = AdvisoryConfig.from_project({})
    assert cfg.enabled is True
    assert cfg.deep_enabled is True


def test_overrides_from_global_settings():
    project = {"global_settings": {"advisory": {"enabled": False, "deep_enabled": False}}}
    cfg = AdvisoryConfig.from_project(project)
    assert cfg.enabled is False
    assert cfg.deep_enabled is False


def test_unknown_subkeys_ignored():
    project = {"global_settings": {"advisory": {"enabled": False, "bogus": 1}}}
    cfg = AdvisoryConfig.from_project(project)
    assert cfg.enabled is False
    assert cfg.deep_enabled is True   # missing -> default
