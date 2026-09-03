.PHONY: help install report charts export validate insights test lint notebook all clean

help:
	@echo "install   - install dependencies and the package in editable mode"
	@echo "report    - print the Summary and Overview dashboards to the terminal"
	@echo "charts    - render the six Overview charts to reports/figures/"
	@echo "export    - export every aggregation to reports/tables/*.csv"
	@echo "validate  - run the data validation suite (non-zero exit on a blocking failure)"
	@echo "insights  - print the risk and business-insight tables"
	@echo "all       - validate, then report, charts and export"
	@echo "notebook  - launch Jupyter"
	@echo "test      - run the test suite"
	@echo "lint      - run ruff"
	@echo "clean     - remove generated outputs and caches"

install:
	python -m pip install --upgrade pip
	python -m pip install -r requirements-dev.txt
	python -m pip install -e .

report:
	python -m bank_loan_report report

charts:
	python -m bank_loan_report charts

export:
	python -m bank_loan_report export

validate:
	python -m bank_loan_report validate

insights:
	python -m bank_loan_report insights

all: validate report charts export

notebook:
	jupyter notebook notebooks/01_bank_loan_analysis.ipynb

test:
	pytest

lint:
	ruff check src tests

clean:
	rm -rf reports/tables reports/sample reports/figures/*.png .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
