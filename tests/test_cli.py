"""
Tests for smard_utils/utils/cli.py.

Covers:
  create_parser, resolve_data_path, load_config_file,
  resolve_capacity_power, apply_config (all branches)
"""
import argparse
import json
import os
import tempfile
import pytest

from smard_utils.utils.cli import (
    create_parser,
    resolve_data_path,
    load_config_file,
    resolve_capacity_power,
    apply_config,
)


# ---------------------------------------------------------------------------
# create_parser
# ---------------------------------------------------------------------------

class TestCreateParser:

    def test_default_strategy_and_region(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge", "de")
        args = parser.parse_args([])
        assert args.strategy == "dynamic_discharge"
        assert args.region == "de"
        assert args.data is None
        assert args.year is None
        assert args.config is None
        assert args.capacity is None
        assert args.power is None

    def test_strategy_override_short(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge")
        args = parser.parse_args(["-s", "day_ahead"])
        assert args.strategy == "day_ahead"

    def test_strategy_override_long(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge")
        args = parser.parse_args(["--strategy", "price_threshold"])
        assert args.strategy == "price_threshold"

    def test_region_override(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge", "de")
        args = parser.parse_args(["-r", "lu"])
        assert args.region == "lu"

    def test_data_path_override(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge")
        args = parser.parse_args(["-d", "/my/data.csv"])
        assert args.data == "/my/data.csv"

    def test_year_override(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge")
        args = parser.parse_args(["-y", "2023"])
        assert args.year == 2023

    def test_capacity_and_power(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge")
        args = parser.parse_args(["--capacity", "1", "5", "10",
                                   "--power", "0.5", "2.5", "5"])
        assert args.capacity == [1.0, 5.0, 10.0]
        assert args.power == [0.5, 2.5, 5.0]

    def test_config_path(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge")
        args = parser.parse_args(["-c", "my.conf"])
        assert args.config == "my.conf"

    def test_default_region_lu(self):
        parser = create_parser("testprog", "desc", "dynamic_discharge", "lu")
        args = parser.parse_args([])
        assert args.region == "lu"


# ---------------------------------------------------------------------------
# resolve_data_path
# ---------------------------------------------------------------------------

class TestResolveDataPath:

    def test_returns_explicit_data_path(self):
        args = argparse.Namespace(data="/explicit/path.csv", region="de")
        result = resolve_data_path(args)
        assert result == "/explicit/path.csv"

    def test_builds_path_from_pattern_when_no_data(self):
        args = argparse.Namespace(data=None, region="de")
        result = resolve_data_path(args)
        assert "de" in result
        assert result.endswith(".csv")

    def test_region_lu_in_default_path(self):
        args = argparse.Namespace(data=None, region="lu")
        result = resolve_data_path(args)
        assert "lu" in result

    def test_custom_pattern(self):
        args = argparse.Namespace(data=None, region="de")
        result = resolve_data_path(args, pattern="data/{region}/test.csv")
        assert result.endswith("data/de/test.csv")


# ---------------------------------------------------------------------------
# load_config_file
# ---------------------------------------------------------------------------

class TestLoadConfigFile:

    def test_loads_dict(self, tmp_path):
        config = {"year": 2023, "fix_price": 0.30}
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(config))
        result = load_config_file(str(p))
        assert result == config

    def test_boolean_true(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text('{"fix_contract": true}')
        result = load_config_file(str(p))
        assert result["fix_contract"] is True

    def test_boolean_false(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text('{"fix_contract": false}')
        result = load_config_file(str(p))
        assert result["fix_contract"] is False

    def test_nested_values(self, tmp_path):
        config = {"a": 1, "b": 2.5, "c": "hello"}
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(config))
        assert load_config_file(str(p)) == config


# ---------------------------------------------------------------------------
# resolve_capacity_power
# ---------------------------------------------------------------------------

class TestResolveCapacityPower:

    def test_both_none_returns_defaults(self):
        args = argparse.Namespace(capacity=None, power=None)
        cap, pwr = resolve_capacity_power(args, [1, 5, 10], [0.5, 2.5, 5])
        assert cap == [1, 5, 10]
        assert pwr == [0.5, 2.5, 5]

    def test_both_set_returns_custom(self):
        args = argparse.Namespace(capacity=[2.0, 8.0], power=[1.0, 4.0])
        cap, pwr = resolve_capacity_power(args, [1, 5], [0.5, 2.5])
        assert cap == [2.0, 8.0]
        assert pwr == [1.0, 4.0]

    def test_only_capacity_raises(self):
        args = argparse.Namespace(capacity=[1.0, 5.0], power=None)
        with pytest.raises(ValueError, match="together"):
            resolve_capacity_power(args, [1], [0.5])

    def test_only_power_raises(self):
        args = argparse.Namespace(capacity=None, power=[0.5, 2.5])
        with pytest.raises(ValueError, match="together"):
            resolve_capacity_power(args, [1], [0.5])

    def test_mismatched_lengths_raises(self):
        args = argparse.Namespace(capacity=[1.0, 5.0, 10.0], power=[0.5, 2.5])
        with pytest.raises(ValueError, match="same number"):
            resolve_capacity_power(args, [1], [0.5])

    def test_single_element_lists(self):
        args = argparse.Namespace(capacity=[5.0], power=[2.5])
        cap, pwr = resolve_capacity_power(args, [1], [0.5])
        assert cap == [5.0]
        assert pwr == [2.5]


# ---------------------------------------------------------------------------
# apply_config
# ---------------------------------------------------------------------------

class TestApplyConfig:

    def test_applies_overrides_from_file(self, tmp_path):
        config = {"year": 2022, "constant_biogas_kw": 500}
        p = tmp_path / "test.json"
        p.write_text(json.dumps(config))

        bds = {"year": 2024, "constant_biogas_kw": 1000}
        args = argparse.Namespace(config=str(p))
        apply_config(bds, args)

        assert bds["year"] == 2022
        assert bds["constant_biogas_kw"] == 500

    def test_no_config_leaves_dict_unchanged(self):
        bds = {"year": 2024}
        args = argparse.Namespace(config=None)
        apply_config(bds, args)
        assert bds == {"year": 2024}

    def test_nonexistent_config_file_prints_warning(self, capsys):
        bds = {"year": 2024}
        args = argparse.Namespace(config="/nonexistent/cfg.json")
        apply_config(bds, args)
        out = capsys.readouterr().out
        assert "not found" in out
        assert bds["year"] == 2024  # dict unchanged

    def test_auto_detect_conf_in_cwd(self, tmp_path, monkeypatch):
        config = {"year": 2021}
        conf = tmp_path / "basic_data_set.conf"
        conf.write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        bds = {"year": 2024}
        args = argparse.Namespace(config=None)
        apply_config(bds, args)
        assert bds["year"] == 2021

    def test_boolean_in_config_is_preserved(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text('{"fix_contract": true}')
        bds = {"fix_contract": False}
        args = argparse.Namespace(config=str(p))
        apply_config(bds, args)
        assert bds["fix_contract"] is True

    def test_returns_updated_dict(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text('{"x": 99}')
        bds = {}
        args = argparse.Namespace(config=str(p))
        result = apply_config(bds, args)
        assert result is bds
        assert result["x"] == 99
