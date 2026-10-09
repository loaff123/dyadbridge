# dyadbridge

Generate possible unobserved jumps between two observed states of a small continuous-time Markov chain. Inputs are exact rationals. Outputs are ordered, quantized event records with an exact rational bound on omitted conditional probability.

This is standard uniformization with a deliberately bounded arithmetic/output contract. It is not a new sampling algorithm or a general exact continuous-timestamp sampler.

## Generate histories

From a source checkout, install with `python -m pip install .`, then:

```sh
dyadbridge sample examples/hky.json --start A --end G --t1 1/5 \
  --samples 100 --seed 17 --time-bits 16 --output histories.jsonl

dyadbridge sample examples/hky.json --start A --end G --t1 1/5 \
  --samples 100 --seed 17 --time-bits 16 --format csv --output events.csv
```

The published four-state HKY example reconstructs nucleotide substitution histories between an observed A and G. The horizon `1/5` is this example's illustrative choice. See [model provenance](docs/provenance.md). Small generated JSONL/CSV examples are included under `examples/`.

A real event row looks like:

```json
{"bin":74,"event_index":0,"from":"A","record_type":"event","sample_id":0,"time":"37/640","to":"G","uniformization_ordinal":1}
```

The exact generated rows in `examples/hky-events.jsonl` are authoritative examples; event times are rational strings, and bins are integers. Each complete stream has a run header, a header for every sample including zero-event samples, real-event rows, and a completion footer. CSV keeps event fields flat; filter `record_type == "event"`. Metadata and sample summaries occupy quoted JSON cells. Large-model metadata may exceed Python csv's default 128KiB field limit or spreadsheet cell limits; use JSONL or [the bounded CSV-reader example](examples/read_csv_events.py), which restores the previous field setting afterward.

## Python API

```python
from dyadbridge import Model, BridgeRequest, prepare, sample_batch

model = Model.from_dict({
    "schema": "dyadbridge.model.v1",
    "states": ["off", "on"],
    "rates": [
        {"from": "off", "to": "on", "rate": "1/1000000000000000000"},
        {"from": "on", "to": "off", "rate": 1},
    ],
})
request = BridgeRequest.from_dict({
    "start": "off", "end": "on", "t0": 0, "t1": 1,
    "epsilon": "1/1000000000000", "time_bits": 32,
}, model)
prepared = prepare(model, request)
batch = sample_batch(prepared, samples=10, seed=17)
print(prepared.certificate.tv_upper)
for line in batch.to_jsonl():
    print(line, end="")
```

`examples/summarize_histories.py` generates 100 HKY histories, reads the complete JSONL back, and calculates real-transition counts and mean quantized occupation times. The runtime uses only Python's standard library.

## What is guaranteed

- Count and state-sequence probabilities use nonnegative exact integer arithmetic. No floating matrix exponential supplies the conditional normalizer.
- The returned rational certificate bounds count truncation for the specified rational model. The default tolerance is `1/1000000000000` per history. A conservative batch bound is also reported.
- Event times are exactly `t0 + (t1-t0)*bin/2**time_bits`. Independent uniform integer bins are sorted, paired with the skeleton, and virtual self-transitions are removed.
- The total-variation bound applies to this explicitly quantized record law. It does not compare finite-precision timestamps with a continuous path law in total variation. Under the shared-history coupling, corresponding event times move less than one bin width.
- Probability statements assume independent unbiased random bits. The seeded CPython MT19937 source provides tested, noncryptographic replay; a seed does not prove the ideal-bit assumption.

Zero-bin jumps and tied jumps are preserved in order. An event at numeric time `t0` follows the initial observation; this is an ordered event record, not a conventional strictly increasing-time trajectory. `uniformization_ordinal` preserves gaps where virtual jumps were removed. Occupation summaries describe the quantized records; tied intermediate states can have zero occupation.

## Honest operating limits

One finite, homogeneous interval; at most 64 states; shared stochastic-kernel denominator at most 512 bits; uniformization mean at most 64; cutoff at most 256. Preparation also limits arithmetic growth, abstract work and logical storage. Dimensions alone do not promise success: coprime denominators, very rare endpoints or stiff models can be refused. Every probability table and worst-case batch/export bound is prepared before sampling. There is no random-dependent retry or path-discard policy.

Inputs accept JSON integers and exact decimal or `p/q` strings. Floats, exponents, implicit rate inference, duplicate edges and supplied diagonals are rejected. Diagonals are derived. State labels are unique ASCII identifiers. A zero horizon or zero generator with equal endpoints produces an empty history; impossible endpoints are identified separately from resource refusal.

```sh
dyadbridge validate examples/hky.json
dyadbridge prepare examples/hky.json --start A --end G --t1 1/5
# Demonstrates a deterministic refusal, not a low-quality sample:
dyadbridge prepare examples/hky.json --start A --end G --t1 1/5 --max-cutoff 1
```

Existing output files require `--overwrite`. Named files are published atomically on success. Interrupted stdout has no valid completion footer and must not be treated as an unbiased subset or silently retried. Exact integer rejection has finite expected work but no deterministic random-bit bound.

Full-byte replay is within the same package/schema/algorithm/runtime tuple. Tested cross-runtime scientific records agree, while runtime provenance may differ. The reader validates this bounded format, summaries and input/run identity hashes; those hashes do not authenticate every event or prove that a producer sampled correctly.

See [the exact contract](docs/contract.md), [validation and limitations](docs/validation.md), and [credits/provenance](docs/provenance.md). No network access, telemetry, GPU, inference, infinite-state truncation or multi-interval estimation is part of this package.
