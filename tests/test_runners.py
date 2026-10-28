import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

CFG = {"sources": {"justjoinit": True, "nofluffjobs": False, "czyjesteldorado": {"enabled": True, "runner": "local"},
                   "solidjobs": {"enabled": True}, "bulldogjob": {"enabled": False, "runner": "cloud"},
                   "nieistnieje": True}}


def test_bool_means_cloud_runner():
    assert main.active_sources(CFG, "cloud") == ["justjoinit", "solidjobs"]


def test_local_runner_gets_only_local_sources():
    assert main.active_sources(CFG, "local") == ["czyjesteldorado"]


def test_no_runner_means_every_enabled_source():
    assert main.active_sources(CFG, None) == ["justjoinit", "czyjesteldorado", "solidjobs"]


def test_real_config_assigns_czyjesteldorado_to_local():
    import yaml
    cfg = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"),
                              encoding="utf-8"))
    assert main.active_sources(cfg, "local") == ["czyjesteldorado", "linkedin"]
    assert not {"czyjesteldorado", "linkedin"} & set(main.active_sources(cfg, "cloud"))
