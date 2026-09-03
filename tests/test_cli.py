"""Tests for the CLI's output routing.

These exist because of a real incident, not a hypothetical one. A
``python -m bank_loan_report --sample charts`` run overwrote the committed
full-dataset figures in ``reports/figures/`` with 600-row versions, and the next
commit published them. The charts still looked plausible - only the axis
magnitudes gave it away - so nothing failed loudly. The fix is that a
``--sample`` run defaults to ``reports/sample/`` and can never touch the
published figures, and these tests pin that behaviour.

They also pin the second half of the fix: ``--outdir`` now means the same thing
for ``charts`` and ``export``. Previously ``charts --outdir X`` wrote to ``X/``
while ``export --outdir X`` wrote to ``X/tables/``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pytest

from bank_loan_report import cli, config


def _args(sample: bool) -> argparse.Namespace:
    return argparse.Namespace(sample=sample)


class TestDefaultOutdir:
    def test_full_run_charts_go_to_the_published_figures_directory(self) -> None:
        assert cli._default_outdir(_args(sample=False), "figures") == config.FIGURES_DIR

    def test_full_run_tables_go_to_the_reports_tables_directory(self) -> None:
        assert cli._default_outdir(_args(sample=False), "tables") == config.TABLES_DIR

    def test_sample_run_charts_do_not_go_to_the_published_figures_directory(self) -> None:
        """The regression this whole module exists for."""
        outdir = cli._default_outdir(_args(sample=True), "figures")
        assert outdir != config.FIGURES_DIR
        assert outdir == config.SAMPLE_FIGURES_DIR

    def test_sample_run_tables_do_not_go_to_the_published_tables_directory(self) -> None:
        outdir = cli._default_outdir(_args(sample=True), "tables")
        assert outdir != config.TABLES_DIR
        assert outdir == config.SAMPLE_TABLES_DIR

    def test_sample_outputs_live_under_the_sample_reports_directory(self) -> None:
        for kind in ("figures", "tables"):
            outdir = cli._default_outdir(_args(sample=True), kind)
            assert config.SAMPLE_REPORTS_DIR in outdir.parents or outdir == config.SAMPLE_REPORTS_DIR

    def test_missing_sample_attribute_is_treated_as_a_full_run(self) -> None:
        """``report``/``quality`` namespaces are built by the same parser."""
        assert cli._default_outdir(argparse.Namespace(), "figures") == config.FIGURES_DIR


class TestExportOutdirIsFlat:
    """``export --outdir X`` must write ``X/*.csv``, not ``X/tables/*.csv``."""

    def test_explicit_outdir_receives_the_csvs_directly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "ensure_output_dirs", lambda: None)
        rc = cli.main(["--sample", "export", "--outdir", str(tmp_path)])
        assert rc == 0
        csvs = sorted(p.name for p in tmp_path.glob("*.csv"))
        assert csvs, "export wrote no CSVs into the directory it was given"
        assert "summary_kpis.csv" in csvs
        assert not (tmp_path / "tables").exists(), "export created a hidden subdirectory"

    def test_charts_and_export_interpret_outdir_the_same_way(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "ensure_output_dirs", lambda: None)
        figs, tables = tmp_path / "figs", tmp_path / "tabs"
        assert cli.main(["--sample", "charts", "--outdir", str(figs), "--risk-only"]) == 0
        assert cli.main(["--sample", "export", "--outdir", str(tables)]) == 0
        # Both land their files at depth 1 inside the directory they were handed.
        assert list(figs.glob("*.png"))
        assert list(tables.glob("*.csv"))


class TestSampleRunCannotTouchPublishedFigures:
    def test_sample_charts_write_only_inside_the_sample_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redirect REPORTS_DIR, then prove the published path is never created."""
        monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
        monkeypatch.setattr(config, "FIGURES_DIR", tmp_path / "figures")
        monkeypatch.setattr(config, "TABLES_DIR", tmp_path / "tables")
        monkeypatch.setattr(config, "SAMPLE_REPORTS_DIR", tmp_path / "sample")
        monkeypatch.setattr(config, "SAMPLE_FIGURES_DIR", tmp_path / "sample" / "figures")
        monkeypatch.setattr(config, "SAMPLE_TABLES_DIR", tmp_path / "sample" / "tables")
        monkeypatch.setattr(config, "ensure_output_dirs", lambda: None)

        assert cli.main(["--sample", "charts", "--risk-only"]) == 0

        assert list((tmp_path / "sample" / "figures").glob("*.png"))
        assert not (tmp_path / "figures").exists(), (
            "a --sample run wrote into the published figures directory"
        )


class TestSampleDataIsActuallySmaller:
    """Guards the assumption that makes the mix-up detectable at all."""

    def test_the_sample_is_a_small_fraction_of_the_full_dataset(self) -> None:
        sample = pd.read_csv(config.SAMPLE_CSV_PATH)
        assert len(sample) < 2_000, "sample CSV is no longer a small sample"
