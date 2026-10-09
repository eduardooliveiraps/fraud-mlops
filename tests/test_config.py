from pathlib import Path

import pytest

from fraud.config import EvaluationConfig, SplitConfig, load_config


def test_repo_config_loads():
    cfg = load_config(Path("configs/config.yaml"))
    assert cfg.data.parquet.suffix == ".parquet"
    assert cfg.split.test_months == (6, 7)
    assert cfg.evaluation.target_fpr == 0.05


def test_types_are_converted(config_dict, write_config):
    config_dict["evaluation"]["cost_false_positive"] = 1  # int is accepted as a number
    cfg = load_config(write_config(config_dict))
    assert cfg.data.raw_csv == Path(config_dict["data"]["raw_csv"])
    assert isinstance(cfg.split.train_months, tuple)
    assert cfg.evaluation.cost_false_positive == 1.0


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(("text", "error"), [("", "must be a mapping"), ("- a\n", "mapping")])
def test_root_not_a_mapping(write_config, text, error):
    with pytest.raises(ValueError, match=error):
        load_config(write_config(text))


def _set(section: str, key: str, value):
    def edit(cfg):
        cfg[section][key] = value

    return edit


def _drop(section: str, key: str):
    def edit(cfg):
        del cfg[section][key]

    return edit


@pytest.mark.parametrize(
    ("edit", "error"),
    [
        (lambda c: c.pop("split"), "missing keys: \\['split'\\]"),
        (lambda c: c.update(extra=1), "unknown keys: \\['extra'\\]"),
        (lambda c: c.update(data=[1, 2]), "'data' must be a mapping"),
        (_drop("data", "parquet"), "missing keys: \\['parquet'\\]"),
        (_set("data", "parqet", "x"), "unknown keys: \\['parqet'\\]"),
        (_set("data", "raw_csv", 3), "'data.raw_csv' must be a non-empty"),
        (_set("data", "raw_csv", ""), "'data.raw_csv' must be a non-empty"),
        (_set("split", "test_months", "6,7"), "'split.test_months' must be a list of integers"),
        (_set("split", "test_months", [6, 7.5]), "must be a list of integers"),
        (_set("split", "test_months", [True]), "must be a list of integers"),
        (_set("split", "valid_months", []), "must all be non-empty"),
        (_set("split", "valid_months", [4]), "time order"),
        (_set("evaluation", "target_fpr", "5%"), "'evaluation.target_fpr' must be a number"),
        (_set("evaluation", "target_fpr", 0), "target_fpr must be in \\(0, 1\\)"),
        (_set("evaluation", "target_fpr", 1.0), "target_fpr must be in \\(0, 1\\)"),
        (_set("evaluation", "cost_false_negative", -1), "Costs must be > 0"),
        (_drop("evaluation", "cost_false_positive"), "missing keys"),
        (_set("train", "seed", "42"), "'train.seed' must be an integer"),
        (_set("train", "n_jobs", 0), "n_jobs and early_stopping_rounds must be >= 1"),
        (_set("train", "params", [1]), "'train.params' must be a mapping"),
        (_set("mlflow", "model_name", ""), "'mlflow.model_name' must be a non-empty string"),
        (_set("gate", "min_recall_gain", -0.1), "Gate margins must be >= 0"),
        (_set("monitoring", "psi_bins", 1), "psi_bins must be >= 2"),
        (_set("monitoring", "psi_window", 5), "psi_window must be >= psi_bins"),
    ],
)
def test_invalid_config(config_dict, write_config, edit, error):
    edit(config_dict)
    with pytest.raises(ValueError, match=error):
        load_config(write_config(config_dict))


@pytest.mark.parametrize(
    "months",
    [
        ((0, 1, 5), (5,), (6, 7)),  # overlap
        ((0, 1), (6,), (5,)),  # valid after test
        ((3,), (1,), (6,)),  # train after valid
    ],
)
def test_split_config_rejects_bad_order(months):
    with pytest.raises(ValueError, match="time order"):
        SplitConfig(*months)


def test_evaluation_config_rejects_zero_cost():
    with pytest.raises(ValueError, match="Costs must be > 0"):
        EvaluationConfig(target_fpr=0.05, cost_false_negative=20.0, cost_false_positive=0.0)
