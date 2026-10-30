# Pump Main AnchorError log: why the rebuild gap is +14 at most sites and +118 at others

## Problem

Pump Main packets report two recurring error-path CU gaps between the original and the rebuild: +14 at most
`require!` sites and about +118 at some. The +14 is the 14 extra bytes of `programs/pump/` in the log line. Eight
merged READMEs show +118 (for example `pump-v2-token-quote-transfer-fee-boundaries-20261030`, `buy_v2.rs:81`), and none
of them gives a cause. It does not follow from the source path or the error code alone: `AccountTypeNotSupported` is
+118 at `buy_v2.rs:81` and +14 at other sites.

## Claim tested

`AnchorError thrown in {}:{}. Error Code: {}. Error Number: {}. Error Message: {}.` is built with `format!`.
The literal pieces are 71 bytes, and `Arguments::estimated_capacity` doubles that, so the `String` starts at
142 bytes. A message longer than 142 bytes reallocates. The rule under test is:

```
original - rebuild = (L_orig - L_rebuild) + 104 if L_rebuild <= 142 < L_orig
original - rebuild = (L_orig - L_rebuild)       otherwise
```

where `L` is the byte length of the message after `Program log: `.

## Method

Family 1 needs no source or binary change beyond one immediate. At each `error!` site the filename length is a
single `stdw [r10-560], <len>` instruction (31 in the original, 17 in the rebuild at `sweep_fees.rs`). `producer.py`
finds that instruction by its neighbouring `stw [r10-552], <line>`, rewrites the immediate in an in-memory copy of
the image, and runs the same failing `sweep_creator_fee` transaction. This gives one error site at many message
lengths, on each image. Nothing is written to disk and no image is included here. Lengths above the real filename
read the following rodata bytes, which only changes log text.

- `l145-*`: `ConstraintSeeds` at `sweep_fees.rs:145`, 36 lengths, message 124..287 bytes.
- `l123-*`: `NotAuthorized` at `sweep_fees.rs:123`, 5 lengths, message 155..186 bytes (control: never crosses a capacity).
- `unpatched-*`: 8 real sites on the unmodified images.

Family 2 applies the rule, without replaying, to the receipts of 14 merged Pump Main packets:
267 failing cases with exactly one `AnchorError thrown` line and a different line on the two images.
Their file hashes are in `runtime/merged-sites.json.gz`, and the receipts come from rebuilds current when each
packet was made.

| Image | sha256 | Bytes |
| --- | --- | ---: |
| original | `7a19affaa2c6187e04a5fe0ea298cee81fa5eb8c24cfcc30d85f615e89f7b02d` | 10,485,715 |
| rebuild | `ae713165a56752f7e1c6153137842e2b145885180b5c71e21a342afed45bd44b` | 1,934,928 |

The rebuild comes from `scripts/build_partial_candidate.py` with platform-tools v1.44 / cargo-build-sbf 2.1.21, source
tree `9e5d2900ed30981d5766fb101ef120ee198161be`.

## Results

### One site, one image, many lengths

Logged Pump CU at `sweep_fees.rs:145` with only the message length changed:

| Message bytes | Original CU | Rebuild CU | Original - rebuild |
| ---: | ---: | ---: | ---: |
| 124 | 24,250 | 24,250 | 0 |
| 141 | 24,267 | 24,267 | 0 |
| 142 | 24,268 | 24,268 | 0 |
| 143 | 24,373 | 24,373 | 0 |
| 144 | 24,374 | 24,374 | 0 |
| 155 | 24,385 | 24,385 | 0 |
| 284 | 24,514 | 24,514 | 0 |
| 285 | 24,619 | 24,619 | 0 |
| 286 | 24,620 | 24,620 | 0 |

- CU rises by 1 per byte, and by 105 from 142 to 143 bytes and again from 284 to 285 bytes. CU minus length takes exactly
  3 values across the 36 probes: 24,126 up to 142 bytes, 24,230 from 143 to 284, 24,334 from 285. Each step is +104.
- 142 -> 284 -> 568 is capacity doubling, and the second step at 285 is what separates this from a fixed cost above a threshold.
- At the same length the two images cost the same in 36/36 probes. The unpatched +118 at this site is the same
  function evaluated at 155 and 141 bytes.
- The `l123` control stays on one value (20,935) across 5 lengths, and 5/5 are equal between images.

### Real sites

| Site | Error | L original | L rebuild | Gap | Rule | Remainder |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `fee-sum-overflow` | 6024 Overflow | 119 | 105 | 14 | 14 | +0 |
| `reserves-sum-overflow` | 6024 Overflow | 129 | 115 | 14 | 14 | +0 |
| `recipient-default` | 6000 NotAuthorized | 186 | 172 | 14 | 14 | +0 |
| `creator-wrong-recipient` | 2006 ConstraintSeeds | 155 | 141 | 118 | 118 | +0 |
| `spl-source-missing` | 3012 AccountNotInitialized | 184 | 170 | 15 | 14 | +1 |
| `spl-source-foreign-owner` | 6010 AccountTypeNotSupported | 153 | 139 | 119 | 118 | +1 |
| `spl-dest-foreign-owner` | 6010 AccountTypeNotSupported | 153 | 139 | 117 | 118 | -1 |
| `protocol-unlisted` | 6000 NotAuthorized | 188 | 174 | 14 | 14 | +0 |

The three non-zero remainders are the branch polarity differences located in
`pump-sweep-fees-path-cu-20261030`.

### Merged packets

| Group | Cases | Min gap | Max gap | Gap counts |
| --- | ---: | ---: | ---: | --- |
| crosses 142 (`L_rebuild <= 142 < L_orig`) | 107 | 118 | 136 | 118: 101, 119: 3, 126: 1, 136: 2 |
| does not cross | 160 | 10 | 47 | 10: 1, 13: 1, 14: 140, 15: 2, 18: 1, 22: 1, 23: 2, 27: 2, 28: 2, 29: 2, 31: 1, 45: 3, 46: 1, 47: 1 |

Every crossing case has a gap of at least 118, and every other case at most 47. Gaps other than 14 and 118 are
sites where other code before the error also differs. Those remainders are not explained here.

## What this means for matching

The +14 and +104 are both consequences of the file-path bytes in the error site, not of the handler code at
that site. No instruction near a +118 site has to change for that gap to close: at equal message length the two
images cost the same.

## Limits

- `.rs` line digits and `file!()` length decide which band a site falls in, so a source line move across a digit
  boundary can move a site between bands.
- The 104-CU cost is measured for `String` growth at these two capacities only. The reallocation itself is inferred
  from the two thresholds and the `format!` capacity, not observed through a trace.
- `AnchorError caused by account:` lines carry no file path (`quote-mismatch` in the sweep packet shows a gap of 0),
  and `panicked at` lines use a different format and are not covered.
- All state is synthetic, and the probes run on in-memory modified images. Only the `unpatched-*` rows and family 2 are
  unmodified binaries.

## Reproduce

```
python3 producer.py --root <repo> --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}' --out <packet>
python3 verify.py --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}'
```

`verify.py` checks the manifest and image sha256 values, replays every probe on both images, and compares receipts and
analysis. With `--root <repo>` it also re-reads the merged packets' receipts behind `runtime/merged-sites.json.gz`.

## Files

- `producer.py`, `verify.py`
- `runtime/plan.json.gz`: probes and base cases
- `runtime/receipts.jsonl.gz`: per-image receipts of every probe
- `runtime/merged-sites.json.gz`: per-site gap counts from the merged packets, with source file hashes
- `runtime/report.json.gz`: analysis
