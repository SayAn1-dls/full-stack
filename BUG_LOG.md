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

### Wind app (found while building it)

| ID | Where | What happened | Cause | Fix and regression guard |
|---|---|---|---|---|
| BUG-010 | product | `build_error_model` crashed with "quantile of an empty sample" on a constant forecast | Tied forecast values made every quartile edge equal and left empty buckets | Edges are de-duplicated and empty buckets merged; `test_regression_tied_forecasts_do_not_leave_empty_buckets` |
| BUG-011 | product | Accuracy view crashed with too few samples | A single open-ended bucket had no label (`None / 1000`) | "all forecast levels" label; `test_regression_single_bucket_has_a_label_and_a_view` |
| BUG-012 | product (silent data loss) | At a 00:00 cutoff the API returned 22 hours and said nothing | The newest run only looks ~46.5 h ahead, so the last two hours had no forecast and were skipped silently | `hours_without_forecast` in the API, a UI notice, tests (API and Playwright) |
| BUG-013 | product (UX) | The planning band had a visible notch around 14:00 | Hard quartile buckets: the band jumped when the forecast crossed an edge | Interpolation between bucket centres; `test_interval_changes_smoothly_across_a_bucket_edge` |
| BUG-014 | UI | Axis unit label overlapped the top tick; histogram reference labels overlapped; x ticks collided on a phone | Fixed offsets, no tick thinning | Layout fixes, `thin()` with unit tests, re-checked by screenshots at desktop and 390px |
| BUG-015 | UI copy and my reading | Subtitles said "the whole distribution sits right of zero" and "the bigger the forecast, the bigger the over-forecast"; I also misread the bias-removal metric as "87% systematic" | Over-claiming; bias/MAE is not the same as the share of error a constant correction removes | Copy made precise (85% of hours; "top quartile"); the correct reading is that removing the bias cuts MAE by about a third (2,091 to 1,416 MW) |
| BUG-016 | test gap | Mutation testing: changing the band's P90 to P80 survived | Tests only checked that the edges were ordered | `test_regression_band_edges_are_exactly_the_stated_percentiles` and the real-data calibration test (78.4% coverage); the mutation is now caught |
| BUG-017 | test | Two assertions ended in `or True` and one test was named for a 404 but asserted a 200 | Careless edits, found on review | Replaced with real assertions; `grep "or True" backend/tests` is clean |
| BUG-018 | test | Wrong assumption that every WINDFOR run looks 60+ hours ahead; a Playwright hover landed off-screen; a route-path assertion broke on FastAPI 0.162 internals | Assumptions about the data and tools | Reach asserted as 46.5-66.5 h from the data; chart scrolled into view; assertion via the OpenAPI schema |

### Deployment (found while shipping it)

| ID | Where | What happened | Cause | Fix and regression guard |
|---|---|---|---|---|
| BUG-019 | process | Uploading the snapshot to Vercel in pieces failed the platform's SHA-1 check | My copy of a base64 part was corrupted; the check did its job | Abandoned file-by-file upload and deployed from the public Git source instead; the unused gzip-parts loader was never committed. A bundle-completeness test (`test_vercel_config.py`) guards what the function ships |
| BUG-020 | process | `create_git_project` was refused (`repo_no_access`) | The connected Vercel account cannot reach this GitHub repository | Empty project plus a deployment from the public Git source; the project is therefore not Git-linked and does not auto-deploy (DECISIONS D-34) |
| BUG-021 | my own tooling | `pkill -f "uvicorn ..."` terminated my own shell (exit 144) whenever the same command line contained the pattern | The pattern matched the shell running the command | Kill by PID, in a separate command |

### Demo video (found while making it)

| ID | Where | What happened | Cause | Fix and regression guard |
|---|---|---|---|---|
| BUG-022 | video process | First cut spoke at about 180 words per minute, too fast for beginner-level English | Kokoro at speed 0.92 | Speed 0.87 (160-170 wpm) and a few sentences trimmed so Part 2 stays under 5:00 (4:46) |
| BUG-023 | video process | A speech-recognition pass heard "FastAPI" as "fast to pi" and "Elexon" as "Alexa" | The voice engine read the spelled-out "Fast A P I" with a schwa, and stressed the second syllable of "Elexon" | "FastAPI" as one word; the phonemes for "Elexon" are overridden; re-checked |
| BUG-024 | video process | The cut showed an empty white page (or the docs page's loading spinner) for about a second when switching from a slide to a live page | Page-load time through the sandbox proxy; pre-loading the pages in a second tab did not remove it | `assemble.py` holds the previous frame wherever the browser shows an empty white page; checked on the final cut |
| BUG-025 | video process | The first caption cue came out as `00:00:00,1000`, invalid SRT | Milliseconds were rounded separately from seconds | Time is rounded once; all 108 cues validated (format, order, no overlap) |
| BUG-026 | video process | In the male voice, a speech-recognition pass heard "endpoints" as "in points" and "meta" as "matter" | American flapped t in "meta"; "endpoints" run together | Spoken as "end points" and "meh-tah" (captions keep the real spelling); re-heard correctly. "Now, our key practices" became "the key practices" because "our" was heard as "are" |

Core cleaning logic (timestamps, zero-nulling, flags, structural NA, uniqueness, completeness) had no defect surfaced by the
test suite. Mutation checks confirm the tests can fail: ignoring DST, dropping the `tsd` rule, filling unpublished columns with 0,
an off-by-one threshold, and over-nulling on real data were each caught (see TEST_REPORT.md).
