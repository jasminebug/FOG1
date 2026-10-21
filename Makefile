.PHONY: install test quick experiments report check all clean
install:
	pip install -r requirements.txt
test:
	python -m pytest -q tests
quick:
	python experiments/run_experiments.py --quick
experiments:
	python experiments/run_experiments.py --workers 4
report:
	python analysis/make_report.py
check:
	python analysis/check_paper_numbers.py
all: test experiments report check
clean:
	rm -rf results/quick results/raw/*.partial
