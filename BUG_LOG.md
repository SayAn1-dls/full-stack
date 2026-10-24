# Bug log

Honest record of defects found while building and testing the pipeline. "Product" means the delivered code or reports; "test"
means the test code was wrong and the pipeline was right. No test was deleted, skipped or weakened to get green: every
failure was diagnosed and the wrong side was fixed.

| ID | Where | What happened | Cause | Fix and regression guard |
|---|---|---|---|---|
| BUG-001 | product (audit report) | `reference_checks.json` reported `kept_rows_stamped_with_nonexistent_local_time = 64` for the noNaN file | One counter mixed two different things: 32 stamps that never existed (spring forward) and 32 that happened twice (autumn back) | Split into `..._nonexistent_local_time` (32) and `..._ambiguous_local_time` (32). Guarded by `test_nonan_file_defects_reproduce` (asserts 32 == 32). Found by reading the output before trusting it |
| BUG-002 | product (audit report) | First holiday-comparison output labelled five weekend Christmas Days `extra_in_combined_file`, and my hand estimate of the disagreements (about 5) was wrong | Label was imprecise; estimate came from comparing against the nominal list rather than the observed definition | Label is now `flagged_in_combined_file_but_falls_on_weekend`; actual count is 10 (5 + 5). Guarded by `test_is_holiday_recomputed_and_every_disagreement_reported`, which lists all 10 dates |
| BUG-003 | product (docs) | First draft of the cleaning report had a garbled row-count formula, a nonsense sentence about which row carries two flags, and claimed the combined file "matches no other nation" | Drafting errors, caught on re-read against `run_manifest.json` / `reference_checks.json` | Corrected (12 x 17,520 + 3 x 17,568 + 16,320; the double-flag row is 2011-02-02 p25; England = Wales tie at 10 disagreements). The data dictionary is now generated and a test fails if it drifts; the report's numbers are each asserted by a real-data test |
| BUG-004 | test | Constant-column test saw an extra constant column | Fixture gave `embedded_wind_capacity` the same value on every row; the pipeline was right to report it | Fixture varies capacity per row |
| BUG-005 | test | End-to-end fixture raised `TimeContinuityError` | Fixture jumped from 2022-12-26 to 2023-01-01 (a real 5-day gap); the pipeline was right | Fixture now covers 2022-12-24..31 contiguous with 2023-01-01 |
| BUG-006 | test | Missing-raw-file test raised "overlaps" instead of "missing" | Test wrote outputs inside the (empty) raw directory, so the raw-directory guard fired first | Test uses a separate empty raw dir. The guard is separately covered by `test_outputs_inside_the_raw_directory_are_refused` |
| BUG-007 | test | Time-axis equality failed on `datetime64[ns]` vs `[us]` | `pd.date_range` defaults to microseconds in pandas 3; values were identical | Built with `unit="ns"` |
| BUG-008 | test | `test_negative_flows_keep_their_sign` failed for `greenlink_flow` | Wrong assumption: a constant-0 column cannot have negatives | Test excludes it and asserts it is all 0 |
| BUG-009 | process | A placeholder expression and a stub function were left in `reference_checks.py` and a test after an edit | Careless edit | Removed immediately; `grep` for `if False` / the stub name is clean and the suite passes without them |

Core cleaning logic (timestamps, zero-nulling, flags, structural NA, uniqueness, completeness) had no defect surfaced by the
test suite. Mutation checks confirm the tests can fail: ignoring DST, dropping the `tsd` rule, filling unpublished columns with 0,
an off-by-one threshold, and over-nulling on real data were each caught (see TEST_REPORT.md).
