"""Static validation of the SQL layer.

There is no SQL Server in CI, so these scripts cannot be executed here. That is
a real limitation and it is stated plainly in ``docs/VERIFICATION.md``. What
*can* be verified without a server is quite a lot:

* every script parses as valid T-SQL (catches typos, unbalanced parentheses,
  a stray comma before FROM - the errors that actually happen);
* the business rules are spelled the same way in every script, so SQL and
  Python cannot drift apart on what counts as a bad loan;
* the analytical script really does use the techniques its documentation
  claims (CTEs, window functions, a join);
* nothing destructive was left in an analysis script.

``sqlglot`` is a dev-only dependency (see ``requirements-dev.txt``); the tests
skip rather than fail if it is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

sqlglot = pytest.importorskip("sqlglot", reason="sqlglot is a dev-only dependency")

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SQL_FILES = sorted(SQL_DIR.glob("*.sql"))
ANALYTICAL_SCRIPT = SQL_DIR / "06_risk_and_cohort_analysis.sql"


def _batches(text: str) -> list[str]:
    """Split a script on the T-SQL ``GO`` batch separator.

    ``GO`` is a client-side directive, not a SQL statement, so a parser has to
    be handed the batches separately.
    """
    return [b for b in text.split("\nGO") if b.strip()]


def test_sql_directory_is_not_empty():
    assert SQL_FILES, f"no .sql files found in {SQL_DIR}"


def test_scripts_are_numbered_in_run_order():
    """The README documents 01 -> 06; the filenames must match that promise."""
    prefixes = [f.name[:2] for f in SQL_FILES]
    assert prefixes == [f"{i:02d}" for i in range(1, len(SQL_FILES) + 1)], prefixes


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_script_parses_as_tsql(path: Path):
    text = path.read_text(encoding="utf-8")
    statements = []
    for batch in _batches(text):
        try:
            statements.extend(sqlglot.parse(batch, dialect="tsql"))
        except sqlglot.errors.ParseError as exc:  # pragma: no cover - failure path
            pytest.fail(f"{path.name} failed to parse: {exc}")
    assert statements, f"{path.name} parsed to zero statements"


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_business_rules_are_spelled_consistently(path: Path):
    """The good/bad loan definition must be identical everywhere.

    A single mis-spelled status string ('Charged off' instead of
    'Charged Off') would silently zero out the bad-loan KPIs, and SQL string
    comparison is case-insensitive by default in SQL Server, so the mistake
    would not surface as an error - just as a wrong number.
    """
    text = path.read_text(encoding="utf-8")
    for wrong in ("'Charged off'", "'charged off'", "'Fully paid'", "'fully paid'"):
        assert wrong not in text, f"{path.name} uses {wrong}; expected exact source casing"


def test_bulk_insert_sets_dateformat():
    """The CSV stores dates as DD-MM-YYYY. Loading it without
    ``SET DATEFORMAT dmy`` makes SQL Server read them month-first, which does
    not error - it silently produces wrong dates for every day <= 12, and
    every KPI in the project is time-sliced."""
    load_script = SQL_DIR / "01_schema_and_load.sql"
    text = load_script.read_text(encoding="utf-8")
    assert "BULK INSERT" in text
    assert "SET DATEFORMAT dmy" in text
    # the directive must precede the actual load statement (the earlier
    # occurrence of the phrase is in the prose that explains the two options)
    assert text.index("SET DATEFORMAT dmy") < text.rindex("BULK INSERT")


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_period_boundaries_are_derived_not_hard_coded(path: Path):
    """MTD/PMTD windows must be computed from MAX(issue_date).

    Hard-coding 'December 2021' would break the moment the dataset is
    refreshed, and it is the most common way a production-grade SQL layer
    reveals itself. The scripts here use DATEFROMPARTS/DATEADD over
    MAX(issue_date) instead, so no DD-MM-YYYY string literal is ever parsed.
    """
    text = path.read_text(encoding="utf-8")
    body = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith(("--", "/*", "*", "*/"))
    )
    if "@mtd_start" not in body and "@pmtd_start" not in body:
        pytest.skip("script does not compute period boundaries")
    assert "MAX(issue_date)" in body, path.name
    assert "DATEFROMPARTS" in body, path.name
    # no dd-mm-yyyy or mm/dd/yyyy literals anywhere in executable code
    import re

    assert not re.search(r"'\d{2}[-/]\d{2}[-/]\d{4}'", body), path.name


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_no_destructive_statements_outside_the_load_script(path: Path):
    """Only 01_schema_and_load.sql may create or drop objects. An analysis
    script that can drop a table is a footgun for whoever runs it next."""
    if path.name.startswith("01"):
        return
    text = path.read_text(encoding="utf-8").upper()
    for verb in ("DROP TABLE", "TRUNCATE TABLE", "DELETE FROM", "UPDATE DBO."):
        assert verb not in text, f"{path.name} contains {verb}"


# --------------------------------------------------------------------------- #
# the analytical script must contain the techniques it claims to demonstrate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "technique",
    ["ROW_NUMBER()", "RANK()", "DENSE_RANK()", "NTILE(", "LAG(", "OVER (", "PARTITION BY"],
)
def test_analytical_script_uses_window_functions(technique: str):
    text = ANALYTICAL_SCRIPT.read_text(encoding="utf-8")
    assert technique in text, f"06 script is missing {technique}"


def test_analytical_script_uses_ctes_and_a_join():
    text = ANALYTICAL_SCRIPT.read_text(encoding="utf-8").upper()
    assert text.count("WITH ") >= 5, "expected a CTE in most sections"
    assert "JOIN" in text


def test_analytical_script_applies_volume_floors():
    """Every segment cut in this project suppresses thin buckets; a default
    rate computed on 3 loans is noise presented as a finding."""
    text = ANALYTICAL_SCRIPT.read_text(encoding="utf-8").upper()
    assert text.count("HAVING COUNT(*) >=") >= 3


def test_analytical_script_documents_its_denominator():
    """Section 7 measures realised risk on closed loans only. If that caveat is
    ever deleted, the numbers become misleading."""
    text = ANALYTICAL_SCRIPT.read_text(encoding="utf-8")
    assert "'Fully Paid', 'Charged Off'" in text
    assert "closed" in text.lower()


def test_analytical_script_references_the_data_quality_doc():
    text = ANALYTICAL_SCRIPT.read_text(encoding="utf-8")
    assert "docs/DATA_QUALITY.md" in text
