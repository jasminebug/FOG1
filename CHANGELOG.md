# Changelog

## v1.1.0: aligned with the revised manuscript

Simulator behaviour is **unchanged**. Re-running the full campaign reproduces every row of `results/raw/*.csv` exactly (4,740 runs, maximum absolute difference 0).

**Statistics**
- `analysis/make_report.py`:
  - adds the matched-pairs rank-biserial correlation r to Table VIII (`table_tests.csv`);
  - applies Holm–Bonferroni correction over all 40 comparisons of Table XVI (`table_winners.csv`), keeping unadjusted p-values as an exploratory column;
  - adds the trace-derived-workload crossover (Sec. VII-D/VII-H) to `key_numbers.json`.
- New `analysis/check_paper_numbers.py`: checks 377 numbers quoted in the paper against the regenerated results. `make check` runs it.

**Documentation**
- `README.md`, `CITATION.cff` and `LICENSE` now match the revised paper:
  - title and authors (Aswad, Kaur, Rana);
  - repository URL;
  - run count (4,740);
  - "trace-derived workload" terminology;
  - the paper-item → file map;
  - the statistical protocol.
- `DATASET.md`: adds the SHA-256 of the derived trace file and states what the replay does and does not preserve.
- Code comments use the equation numbers of the revised paper: (14), (17)–(21).
- Adds `.gitignore`.
