# Validation and measured limits

This report separates the first hosted qualification from the preserved local validation that preceded publication. The local measurements and frozen distribution documents remain historical snapshots; they have not been relabeled as new local runs.

## First hosted qualification

On 2026-10-09, [GitHub Actions run 37931505912](https://github.com/loaff123/dyadbridge/actions/runs/37931505912) passed all five jobs for [source commit a5d3bd1883d4016a3c1f1a1e3859197d032871ef](https://github.com/loaff123/dyadbridge/tree/a5d3bd1883d4016a3c1f1a1e3859197d032871ef):

- CPython 3.11.17, 3.12.15, 3.13.16 and 3.14.8 each passed all 68 tests with zero skips.
- Each runtime built a wheel and source distribution using the declared setuptools 77.0.3 floor, checked all 49 public source files against the archives, and installed both archives into separate clean environments: eight clean installs in total. Installed API, complete JSONL readback, module/console CLI, bundled assets and absent scientific-runtime-dependency checks passed.
- The separate CPython 3.12.15 oracle job passed all eight independent high-precision cases, including the dense 64-state case. These numerical cross-checks supplement the exact rational argument; they are not proofs.

The hosted jobs built fresh archives from that exact source commit. They did not replace the previously delivered frozen wheel or source distribution, whose bytes and local qualification remain unchanged. The runtime/scientific implementation and resource policy were unchanged by publication. Registry publication is not claimed.

## Preserved local checks

The following checks and the remaining measurements in this report describe the pre-publication local qualification. [validation-results.json](validation-results.json), including its local runtime coverage and source hashes, is retained as that historical evidence.

- The recorded source suite ran 68 tests on CPython 3.12.14 and 3.13.5: 67 passed and one installed-environment fixture was intentionally skipped unless its provisioned interpreter list was supplied. With that list supplied, all 68 passed without skips; the fixture exercised all three local clean-install environments.
- Eight independent analytical/high-precision cases passed at 180 or more decimal digits, with an additional precision check: HKY, rare two-state, birth depths 20/60, periodic two-state, a nonreversible cycle, and dense 8/64-state examples. These numerical checks do not replace the exact rational truncation argument.
- Clean wheel installs on CPython 3.12/3.13 and a clean source-distribution install on 3.12 passed API, complete JSONL readback, module/console CLI, bundled example and absent scientific-runtime-dependency checks. CPython 3.11/3.14 were not part of that local qualification; their first hosted verification is recorded above.
- A 50-history, 106-record replay matched across tested runtimes after removing only runtime provenance.
- The declared setuptools build floor is 77.0.3, tested by actual wheel/sdist builds and an isolated sdist installation. The earlier 68.0.0 floor rejected the SPDX license string; that failure and the build-floor regression were reproduced before correction. This build-only requirement adds no runtime dependency. See the [setuptools SPDX migration guidance](https://setuptools.pypa.io/en/stable/userguide/license_migration.html) and [PyPA pyproject guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
- The pinned, unmodified mbridges full-path sampler completed 1,024 trajectories for each of two ordinary models with zero failures or captured warnings. Each model was compared with 4,096 dyadbridge histories; details follow below.

## Operating envelope

The fixed 40-case matrix produced 36 prepared-and-sampled cases and four deterministic refusals under unchanged ceilings. Each supported case generated 10 histories; each case ran in a fresh process. This is an observed matrix, not universal performance or stochastic-quality evidence.

| Case | Result | Cutoff / reason |
|---|---|---|
| dense 4, mu=1 | prepared-and-sampled | 15 |
| sparse 4, mu=1 | prepared-and-sampled | 15 |
| dense 4, mu=4 | prepared-and-sampled | 25 |
| sparse 4, mu=4 | prepared-and-sampled | 26 |
| dense 4, mu=16 | prepared-and-sampled | 52 |
| sparse 4, mu=16 | prepared-and-sampled | 53 |
| dense 4, mu=64 | prepared-and-sampled | 130 |
| sparse 4, mu=64 | prepared-and-sampled | 130 |
| dense 8, mu=1 | prepared-and-sampled | 15 |
| sparse 8, mu=1 | prepared-and-sampled | 16 |
| dense 8, mu=4 | prepared-and-sampled | 26 |
| sparse 8, mu=4 | prepared-and-sampled | 26 |
| dense 8, mu=16 | prepared-and-sampled | 53 |
| sparse 8, mu=16 | prepared-and-sampled | 53 |
| dense 8, mu=64 | prepared-and-sampled | 131 |
| sparse 8, mu=64 | prepared-and-sampled | 130 |
| dense 32, mu=1 | prepared-and-sampled | 16 |
| sparse 32, mu=1 | prepared-and-sampled | 16 |
| dense 32, mu=4 | prepared-and-sampled | 27 |
| sparse 32, mu=4 | prepared-and-sampled | 26 |
| dense 32, mu=16 | prepared-and-sampled | 54 |
| sparse 32, mu=16 | prepared-and-sampled | 54 |
| dense 32, mu=64 | refused | work_units |
| sparse 32, mu=64 | prepared-and-sampled | 133 |
| dense 64, mu=1 | prepared-and-sampled | 16 |
| sparse 64, mu=1 | prepared-and-sampled | 18 |
| dense 64, mu=4 | prepared-and-sampled | 27 |
| sparse 64, mu=4 | prepared-and-sampled | 29 |
| dense 64, mu=16 | prepared-and-sampled | 55 |
| sparse 64, mu=16 | prepared-and-sampled | 55 |
| dense 64, mu=64 | refused | work_units |
| sparse 64, mu=64 | prepared-and-sampled | 133 |
| rare | prepared-and-sampled | 28 |
| hky | prepared-and-sampled | 9 |
| birth depth 20 | prepared-and-sampled | 25 |
| birth depth 60 | prepared-and-sampled | 64 |
| rare_branch | refused | work_units |
| coprime | refused | kernel_denominator_bits |
| cycle | prepared-and-sampled | 15 |
| periodic | prepared-and-sampled | 129 |

The dense 64-state mu=4 fixture prepared in about 2.12 seconds in this run, with 39,819,576 logical bytes and 106,353 categorical entries. Its measured process peak was 27,736 KiB RSS. Logical-byte accounting deliberately differs from RSS.

The 10^-18 two-state fixture prepared and sampled, but used 4,258,064,513 of 4,294,967,296 preparation work units (about 99.14%). Its rational normalization costs dominate this conservative metric; there is little headroom. Do not generalize its success to arbitrary rare models.

Dense 32/64-state mu=64 cases and the 10^-100 rare branch hit work ceilings. A pairwise-coprime construction hit a 520-bit kernel denominator against the 512-bit limit. No sample was returned for a refused model, and no ceiling was relaxed.

## Reproduce

From the source tree, after installing the package and development oracles:

```sh
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
python validation/analytical.py --output analytical.json
python validation/envelope.py --output envelope.json
python validation/baseline.py --mbridges-source /path/to/pinned/mbridges --deps /path/to/opt-einsum --output baseline.json
```

The baseline source must be the documented pinned, unmodified MIT version. The driver makes no downloads and records every attempt/failure. Its float timestamps are quantized for comparison; near-bin-boundary numerical effects remain possible. Statistical agreement is supplementary to independent exact/analytical checks. R baselines were not executed.

Reference environment: Linux-6.18.44-x86_64-with-glibc2.41. Python 3.12.14. Timings include interpreter/workload effects and are not a speed-superiority claim.

## Full-path ordinary baseline comparison

Both models used 8-bit time bins. The baseline ran its unmodified constructor and full step loop for each seed 0..1023. The dyadbridge batch used seed 20261009. No failed trajectory was discarded or retried; there were no failures/warnings in these runs.

| Model | mbridges mean real jumps | dyadbridge mean real jumps | First-hit midpoint fractions | Difference / combined SE |
|---|---:|---:|---|---:|
| periodic | 1.316406 | 1.319336 | 0.572266 / 0.552734 | 1.13 |
| hky | 1.027344 | 1.034180 | 0.518555 / 0.490479 | 1.61 |

The observed differences are consistent with the disclosed Monte Carlo uncertainty; this is supplementary comparison evidence, not a test that certifies either sampler. Intermediate-state and complete jump-count histograms were also recorded. The symmetric two-state conditional mean jump count has the independent value coth(1), approximately 1.313035.

Baseline elapsed totals were about 158.7 seconds and 148.6 seconds, including per-trajectory construction/eigendecomposition. The dyadbridge timing records use a reusable prepared model. Those different accounting choices are not a controlled speed comparison. NumPy 2.3.5, SciPy 1.17.0 and opt-einsum 3.4.0 were used only for the baseline/development oracles.

A forced 235-event supported history additionally passed with 64-character labels, a 512-bit negative origin, 64-bit bins, all-zero/all-maximum tied bins, both exporter bounds, and exact readback. Work guards were patched to raise after draws; none were consulted. These are explicit constructed test tapes, not claimed seeded scientific samples.

## Final producer/readback closure checks

After the final reader-work repair, each required dense 64-state mu=4, rare 10^-18 two-state, birth-depth 60 and HKY fixture generated 10 histories, exported JSONL and CSV, and passed exact JSONL readback. Configured CSV parsing reconstructed exactly the same records. The initial dense-model CSV parse with Python's default 131,072-character field limit failed on its large metadata cell; the successful comparison explicitly used the declared 8MiB field ceiling and restored the previous setting. JSONL remains the primary full-fidelity format. No default spreadsheet-cell compatibility is claimed.

The independent review also found a deliberately difficult coprime/Fibonacci model whose producer originally passed but whose reader exceeded its normalization-work ceiling. The producer now replays canonical reader ingestion before creating the RNG; that unsupported case refuses at reader-model-preflight. All four required useful cases still complete under unchanged ceilings. The 40-case matrix remains 36 successful cases and 4 explicit refusals after this repair.

Machine-readable local numerical results, explicit refusal reasons and tested source hashes are preserved in [validation-results.json](validation-results.json). Frozen archive digests and local clean-install verification accompany release delivery; the first hosted qualification is recorded separately above.

A final raw-ingestion regression covers a depth-16 input just below 1MiB whose nested containers alone would exceed the 64MiB logical ceiling before unknown-field rejection. A decoded-shape guard now refuses before json.loads, including a malformed trailing-byte variant. Independent shape-envelope checks and overlapping reader-object tests support the targeted accounting fixes; this remains conservative software accounting rather than a formal OS-memory proof.
