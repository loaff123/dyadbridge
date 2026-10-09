# Exact input and output contract

## Inputs and scope

`Model.from_dict` and raw JSON use `dyadbridge.model.v1`, a list of state labels, and directed off-diagonal rate records. Labels match `[A-Za-z][A-Za-z0-9_.-]{0,63}`. State and edge order are canonicalized; zero edges disappear; duplicates and diagonal entries are errors. Rational values are integers or strings matching `-?(0|[1-9][0-9]*)(/[1-9][0-9]*|\.[0-9]+)?`. Canonical exported input values must fit the same 256-character token and 1 MiB model envelopes. Boolean and floating values are rejected.

A request contains start/end labels, rational t0/t1, epsilon in (0,1), and time_bits in 1..64. Sample count (1..10,000) and a required unsigned 64-bit integer seed are separate run options. Rates and times are supplied model facts, not estimates. No bound covers input-model uncertainty.

## Distribution and certificate

Let lambda be the maximum exit rate, R=I+Q/lambda, mu=lambda*T, and beta_n=(R^n)e_end. The unnormalized conditioned count weight is w_n=mu^n*beta_n(start)/n!. The exponential factor cancels. The first supported cutoff K satisfying the requested error is selected. For K+2>mu, the omitted unnormalized mass is at most

`H = [mu**(K+1)/(K+1)!] / [1-mu/(K+2)]`.

With retained mass S, the reported bound is `H/(S+H)`. Exact rational/integer arithmetic establishes this inequality. The implementation stores R=A/D, computes B_n=A^n e_end, and uses integer state masses A_ij*B_(r-1)(j). Its count normalizer and transition kernels come from that same series.

Draw N independent uniform b-bit bins, sort them, pair them with the N conditioned skeleton transitions, and delete unchanged states. This exactly matches floor quantization of the corresponding uniformization event times. Event ordinals retain same-bin order and removed virtual-step positions. The truncation bound survives this projection; the full metadata-bearing record also retains augmented-count information. It is never a continuous-path TV bound.

## Resource contract

Default hard ceilings include: 64 states; 4,032 input edges; 512-bit reduced input parts/shared R denominator; mu<=64; K<=256; 32,768-bit exact-arithmetic intermediates; 262,144 categorical entries; 2^32 abstract arithmetic work units per bounded preparation phase; 64 MiB logical preparation allocation; 128 MiB materialized batch; 512 MiB reader allocation; 256 MiB output; 8 MiB output record; one million maximum event slots; two million logical categorical/bin requests.

Integer work is a deterministic conservative metric weighted by operand bits. Logical storage charges representation owners and overlapping temporary reservations, including conservative maximum-width frames. Neither metric is an OS RSS or elapsed-time guarantee. Raw ingestion has separate bounded work/storage accounting; its spelling-dependent diagnostics do not enter canonical output. Before JSON decoding, a lexical shape bound reserves arrays, object-pairs/dictionary overlap, strings, scalars and input buffers; the decoded-model owner remains charged through semantic conversion. The raw byte cap alone is not treated as a decoded-memory bound. Overly complex input may therefore refuse before schema validation. Equivalent accepted canonical models produce the same preparation diagnostics.

All possible transition tables and worst-case materialized/export/readback bounds are prepared before drawing model randomness. Rejection sampling of an integer ticket has no quota. No path is discarded, no retry is substituted, and no tolerance is silently relaxed when a budget fails. OS failure or interrupted I/O is an incomplete batch, not a filtered valid sample set.

## Format, identity and reading

JSONL record order is run; then one sample header and its real events for each sample; then complete. Every line, including the final footer, ends with LF. Unexpected fields, duplicate keys, missing footer/LF, invalid chains or noncanonical rational spellings are rejected. Timestamps are reduced rational strings; bins/indices/counts are bounded JSON integers. Model/request/run hashes identify canonical inputs and the versioned seeded run; they are not event signatures or provenance proofs.

CSV columns are `record_type,sample_id,event_index,uniformization_ordinal,from,to,bin,time,metadata_json`. Event rows are flat. Other records use canonical quoted JSON metadata. The CSV header and completion row are required for the complete export. The public v0.1 reader accepts binary JSONL streams. Large-model CSV run metadata can exceed Python csv's default 131,072-character field limit and spreadsheet cell limits. For full metadata fidelity, use JSONL or configure a CSV reader's field limit to 8,388,608 while reading, then restore the previous setting. The package does not change global CSV reader settings. Flat event rows remain ordinary CSV; metadata is intentionally a single quoted JSON cell. `examples/read_csv_events.py` enforces the declared field, record and whole-stream ceilings and restores the previous csv.field_size_limit in a finally block, including on failure.

`read_jsonl` is a bounded format/consistency reader. It does not recompute uniformization or certify an untrusted producer. Re-preparation can independently check the deterministic certificate; seeded replay can compare histories. Neither establishes that an external bit source was ideal.

## RNG and reproducibility

The supplied source is CPython `random.Random(integer_seed)` with pinned getrandbits compatibility vectors. Only CPython 3.11–3.14 is admitted; the validation report distinguishes tested releases from unverified ones. A vector mismatch refuses before the run RNG is constructed. Integer categoricals draw `k=(total-1).bit_length()` bits until the ticket is below total, then choose the first larger cumulative mass. Single-option choices consume no bits. Draw order is count, skeleton, then unsorted bins, sample by sample.

Seeded replay is noncryptographic. Full files are byte-identical only within the same package/schema/algorithm/RNG/runtime tuple. Cross-tested-runtime comparisons remove only the runtime metadata object. Reusing a seed reproduces the run; it does not make new independent observations.

## CLI outcomes

Exit 0: success; 2: invalid input/CLI; 3: impossible endpoint; 4: unsupported resource/runtime; 5: I/O; 6: unexpected runtime/invariant error. Diagnostics are JSON on stderr. `--debug` before the subcommand adds a traceback. Output paths are prepared before model sampling. Existing files require explicit `--overwrite`; failed generation preserves the previous target. No automatic retry occurs.
