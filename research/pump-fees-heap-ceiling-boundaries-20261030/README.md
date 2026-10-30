# Pump Fees heap ceilings: where size-driven inputs run out of memory, original vs rebuild

## Problem

Existing Pump Fees packets measure return values, error codes and compute units. None of them measures heap use, and
no script or packet in the repository mentions a ComputeBudget `RequestHeapFrame`. The one existing data point is the
string boundary in `pump-fees-instruction-decode-boundaries-20261030` (declared length 32030 gives error 102, 32031
panics), measured without a heap frame.

The heap is a useful comparison target because a bump allocator's exhaustion point depends on the size, count and order
of allocations. Compute units can match while those differ, so a boundary located to one byte or one element tests
something the CU comparison does not. This packet asks:

1. Does `RequestHeapFrame` give the program more heap?
2. Where does each size-driven input stop working, and with which outcome?
3. Do the original and the rebuild stop at the same place, with the same logs and CU?

## Method

There are 52 families. Each one sweeps a single variable x over one handler. A sweep runs on each image
separately:

- Ranges of at most 2000 are walked point by point. Longer ranges use a fixed grid of about 49 points, plus bisection of
  every neighbouring pair of grid points with different outcome classes, down to adjacent x.
- The outcome class is the transaction error plus the Anchor error code. An out-of-memory panic is its own class (`OOM`).
- Receipts keep CU, a hash of the full log list, the first 160 bytes of each log line, and the return data length and
  hash, for each edge. Grid rows keep the class, CU and log hash.

In total: 12404 grid points and 71 outcome edges, 52 of them edges into `OOM`.

Each transaction sets a 1,400,000 CU limit. Instruction data is limited by the message format to under 65536 bytes.

Stored-length families are synthetic. They place accounts with more stored data than the program can create
(`create_social_fee_pda` caps `user_id` at 20 bytes in a 179-byte account, tier lists cap at 50) and use them as a ruler
for the allocator. Those rows do not describe reachable state.

## Result

**Original and rebuild match on every edge, in position and in both outcome classes, across all 52 families.**
Grid classes also match at every point. CU and logs match at every grid point and edge receipt except three `get_fees`
points on an empty tier list, listed under Differences.

### RequestHeapFrame has no effect on the heap the program can use

Both images are charged for the frame, and neither gets more usable heap from it. A frame at the default size adds 150
CU, each further 32 KiB page (or part of one) adds 8, and the boundary stays where it was.

| RequestHeapFrame (bytes) | CU at declared length 1 | CU minus the no-frame run | last declared length that is not OOM (both images) |
|---|---|---|---|
| none | 1916 | 0 | 32030 |
| 32768 | 2066 | 150 | 32030 |
| 33792 | 2074 | 158 | 32030 |
| 65536 | 2074 | 158 | 32030 |
| 131072 | 2090 | 174 | 32030 |
| 262144 | 2122 | 206 | 32030 |

The same holds for the other input shapes at the largest frame:

| family | no frame: edges | 262144-byte frame: edges |
|---|---|---|
| `ascii-body-create_social_fee_pda` | 16182 | 16182 |
| `tier-vec-update_fee_config` | 408 | 408 |
| `holder-vec-update_fee_shares` | 480 | 480 |
| `claim-pays` | 834, 2172 | 834, 2172 |

So the usable heap behaves as a fixed 32 KiB on both images, whatever frame is requested.

### Incoming data, no accounts

These families stop at the argument decoder or just after it. The handler body never runs.

| family | handler | x | edge: last x -> x+1 | CU at x | CU at x+1 | event logged before the OOM | orig = rebuild |
|---|---|---|---|---|---|---|---|
| `declared-string-create_social_fee_pda` | create_social_fee_pda | declared user_id length, no body, no accounts | 32030: InstructionDidNotDeserialize -> OOM | 2034 | 1796 | no | yes |
| `declared-string-claim_social_fee_pda` | claim_social_fee_pda | declared user_id length, no body, no accounts | 32030: InstructionDidNotDeserialize -> OOM | 2037 | 1799 | no | yes |
| `declared-string-claim_social_fee_pda_v2` | claim_social_fee_pda_v2 | declared user_id length, no body, no accounts | 32030: InstructionDidNotDeserialize -> OOM | 2040 | 1802 | no | yes |
| `ascii-body-create_social_fee_pda` | create_social_fee_pda | user_id length with an ASCII body, no accounts | 16182: AccountNotEnoughKeys -> OOM | 20893 | 20233 | no | yes |
| `invalid-utf8-body-create_social_fee_pda` | create_social_fee_pda | user_id length with a 0xff body, no accounts | 31978: InstructionDidNotDeserialize -> OOM | 2746 | 2508 | no | yes |
| `ascii-body-claim_social_fee_pda` | claim_social_fee_pda | user_id length with an ASCII body, no accounts | 16022: AccountNotEnoughKeys -> OOM | 20803 | 20582 | no | yes |
| `invalid-utf8-body-claim_social_fee_pda` | claim_social_fee_pda | user_id length with a 0xff body, no accounts | 31978: InstructionDidNotDeserialize -> OOM | 2749 | 2511 | no | yes |
| `ascii-body-claim_social_fee_pda_v2` | claim_social_fee_pda_v2 | user_id length with an ASCII body, no accounts | 16022: AccountNotEnoughKeys -> OOM | 20807 | 20586 | no | yes |
| `invalid-utf8-body-claim_social_fee_pda_v2` | claim_social_fee_pda_v2 | user_id length with a 0xff body, no accounts | 31978: InstructionDidNotDeserialize -> OOM | 2752 | 2514 | no | yes |
| `tier-vec-update_fee_config` | update_fee_config | Vec<FeeTier> length with a body, no accounts | 408: AccountNotEnoughKeys -> OOM | 22709 | 21306 | no | yes |
| `tier-vec-update_stable_fee_config` | update_stable_fee_config | Vec<FeeTier> length with a body, no accounts | 408: AccountNotEnoughKeys -> OOM | 22702 | 21312 | no | yes |
| `tier-vec-upsert_fee_tiers` | upsert_fee_tiers | Vec<FeeTier> length with a body, no accounts | 408: AccountNotEnoughKeys -> OOM | 22704 | 21309 | no | yes |
| `tier-vec-upsert_stable_fee_tiers` | upsert_stable_fee_tiers | Vec<FeeTier> length with a body, no accounts | 408: AccountNotEnoughKeys -> OOM | 22710 | 21315 | no | yes |
| `holder-vec-update_fee_shares` | update_fee_shares | Vec<Shareholder> length with a body, no accounts | 480: AccountNotEnoughKeys -> OOM | 33517 | 32145 | no | yes |
| `holder-vec-update_fee_shares_v2` | update_fee_shares_v2 | Vec<Shareholder> length with a body, no accounts | 480: AccountNotEnoughKeys -> OOM | 33522 | 32148 | no | yes |

Reading these numbers (inferences from the measured values, not separate measurements):

- **Vec lengths move in doublings.** 408 is 102 x 4, and 480 is 120 x 4. That fits a Vec that starts at
  4096 / element size and doubles: 102, 204, 408 for a 40-byte `FeeTier`, and 120, 240, 480 for a 34-byte `Shareholder`.
  The bump allocator does not reuse the old buffers, so the next growth (816 x 40 = 32640 bytes, on top of 28560 used)
  does not fit. A 48-byte `FeeTier` would put the steps at 85, 170, 340, so both images behave as if the element is 40
  bytes.
- **A string with a body costs about twice its length.** 32030 with no body against 16182 with an ASCII body. That fits
  the argument being decoded a second time for the `#[instruction(user_id, platform)]` attribute. An invalid UTF-8 body
  fails in the first decode and stops at 31978.
- The 160-byte gap between `create_social_fee_pda` (16182) and the claim handlers (16022) is measured. Its cause is not
  isolated here.

### Incoming data, full accounts

| family | handler | x | edge: last x -> x+1 | CU at x | CU at x+1 | event logged before the OOM | orig = rebuild |
|---|---|---|---|---|---|---|---|
| `claim-long-incoming` | claim_social_fee_pda | incoming user_id length with a body, full accounts | 32: ok -> ConstraintSeeds | 25818 | 5137 |  | yes |
| `claim-long-incoming` | claim_social_fee_pda | incoming user_id length with a body, full accounts | 15825: ConstraintSeeds -> OOM | 23115 | 22356 | no | yes |
| `update-incoming-full-accounts` | update_fee_config | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 0: NoFeeTiers -> ok | 11707 | 21781 |  | yes |
| `update-incoming-full-accounts` | update_fee_config | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 50: ok -> TooManyFeeTiers | 61545 | 15517 |  | yes |
| `update-incoming-full-accounts` | update_fee_config | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 204: TooManyFeeTiers -> OOM | 23318 | 20915 | no | yes |
| `update-stable-incoming-full-accounts` | update_stable_fee_config | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 0: NoFeeTiers -> ok | 11652 | 22141 |  | yes |
| `update-stable-incoming-full-accounts` | update_stable_fee_config | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 50: ok -> TooManyFeeTiers | 61905 | 15462 |  | yes |
| `update-stable-incoming-full-accounts` | update_stable_fee_config | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 204: TooManyFeeTiers -> OOM | 23263 | 20861 | no | yes |
| `upsert-incoming-full-accounts` | upsert_fee_tiers | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 0: NoFeeTiers -> ok | 11660 | 21745 |  | yes |
| `upsert-incoming-full-accounts` | upsert_fee_tiers | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 50: ok -> TooManyFeeTiers | 61436 | 15692 |  | yes |
| `upsert-incoming-full-accounts` | upsert_fee_tiers | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 204: TooManyFeeTiers -> OOM | 23515 | 20982 | no | yes |
| `upsert-stable-incoming-full-accounts` | upsert_stable_fee_tiers | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 0: NoFeeTiers -> ok | 11666 | 21987 |  | yes |
| `upsert-stable-incoming-full-accounts` | upsert_stable_fee_tiers | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 50: ok -> TooManyFeeTiers | 61798 | 15642 |  | yes |
| `upsert-stable-incoming-full-accounts` | upsert_stable_fee_tiers | incoming Vec<FeeTier> length, full accounts, 2 stored tiers | 204: TooManyFeeTiers -> OOM | 23465 | 20957 | no | yes |

Tier lists above 50 return `TooManyFeeTiers` up to 204, then run out of memory. A 33-byte `user_id` on a claim fails the
seeds constraint (no PDA exists for a seed over 32 bytes).

### Stored data

| family | handler | x | edge: last x -> x+1 | CU at x | CU at x+1 | event logged before the OOM | orig = rebuild |
|---|---|---|---|---|---|---|---|
| `claim-pays` | claim_social_fee_pda | stored user_id length | 834: ok -> ReturnDataTooLarge | 34411 | 33663 |  | yes |
| `claim-pays` | claim_social_fee_pda | stored user_id length | 2172: ReturnDataTooLarge -> OOM | 46529 | 46390 | yes | yes |
| `claim-pays-uid32` | claim_social_fee_pda | stored user_id length, 32-byte incoming user_id | 834: ok -> ReturnDataTooLarge | 34327 | 33579 |  | yes |
| `claim-pays-uid32` | claim_social_fee_pda | stored user_id length, 32-byte incoming user_id | 2169: ReturnDataTooLarge -> OOM | 46379 | 46240 | yes | yes |
| `claim-nothing-due` | claim_social_fee_pda | stored user_id length | 31768: ok -> OOM | 32940 | 32072 | no | yes |
| `claim-rate-limited` | claim_social_fee_pda | stored user_id length | 31768: ok -> OOM | 32406 | 31538 | no | yes |
| `claim-disabled` | claim_social_fee_pda | stored user_id length | 31678: FeatureDeactivated -> OOM | 32397 | 31740 | no | yes |
| `claim-wrong-authority` | claim_social_fee_pda | stored user_id length | 31291: NotAuthorized -> OOM | 26745 | 25948 | no | yes |
| `claim-v2-native-pays` | claim_social_fee_pda_v2 | stored user_id length | 834: ok -> ReturnDataTooLarge | 41354 | 40447 |  | yes |
| `claim-v2-native-pays` | claim_social_fee_pda_v2 | stored user_id length | 2111: ReturnDataTooLarge -> OOM | 52767 | 52470 | yes | yes |
| `claim-v2-native-nothing-due` | claim_social_fee_pda_v2 | stored user_id length | 30920: ok -> OOM | 39396 | 38374 | no | yes |
| `get-fees-stored-normal` | get_fees | stored fee_tiers length | 0: ProgramFailedToComplete -> ok | 4529 | 3358 |  | see Differences |
| `get-fees-stored-normal` | get_fees | stored fee_tiers length | 408: ok -> OOM | 29655 | 22009 | no | yes |
| `get-fees-stored-stable` | get_fees | stored stable_fee_tiers length | 0: ProgramFailedToComplete -> ok | 4672 | 3501 |  | see Differences |
| `get-fees-stored-stable` | get_fees | stored stable_fee_tiers length | 408: ok -> OOM | 29798 | 22178 | no | yes |
| `update-stored-normal-n1` | update_fee_config | stored fee_tiers length, 1 incoming tier | 408: ok -> OOM | 42330 | 22818 | no | yes |
| `update-stored-normal-n50` | update_fee_config | stored fee_tiers length, 50 incoming tiers | 102: ok -> OOM | 66546 | 28646 | yes | yes |
| `update-stored-stable-n50` | update_fee_config | stored stable_fee_tiers length, 50 incoming tiers | 50: ok -> BorshIoError("failed to write whole buffer") | 74387 | 78020 |  | yes |
| `update-stored-stable-n50` | update_fee_config | stored stable_fee_tiers length, 50 incoming tiers | 102: BorshIoError("failed to write whole buffer") -> OOM | 81395 | 28638 | yes | yes |
| `update-50-stored-both-n50` | update_fee_config | stored stable_fee_tiers length, 50 stored fee_tiers, 50 incoming tiers | 96: ok -> OOM | 88563 | 50133 | yes | yes |
| `upsert-stored-normal-n1` | upsert_fee_tiers | stored fee_tiers length, 1 incoming tier at offset 0 | 50: ok -> TooManyFeeTiers | 36049 | 15467 |  | yes |
| `upsert-stored-normal-n1` | upsert_fee_tiers | stored fee_tiers length, 1 incoming tier at offset 0 | 204: TooManyFeeTiers -> OOM | 23268 | 20823 | no | yes |
| `get-fees-quote-stored-normal` | get_fees_with_quote_mint | stored fee_tiers length | 0: ProgramFailedToComplete -> ok | 4616 | 3444 |  | see Differences |
| `get-fees-quote-stored-normal` | get_fees_with_quote_mint | stored fee_tiers length | 408: ok -> OOM | 29741 | 22023 | no | yes |
| `update-wrong-admin-stored-normal` | update_fee_config | stored fee_tiers length, non-admin signer | 408: InvalidAdmin -> OOM | 26551 | 22818 | no | yes |
| `update-stable-stored-stable-n1` | update_stable_fee_config | stored stable_fee_tiers length, 1 incoming tier | 408: ok -> OOM | 42832 | 22979 | no | yes |
| `upsert-stable-stored-stable-n1` | upsert_stable_fee_tiers | stored stable_fee_tiers length, 1 incoming tier at offset 0 | 50: ok -> TooManyFeeTiers | 36609 | 15615 |  | yes |
| `upsert-stable-stored-stable-n1` | upsert_stable_fee_tiers | stored stable_fee_tiers length, 1 incoming tier at offset 0 | 204: TooManyFeeTiers -> OOM | 23416 | 20971 | no | yes |
| `exotic-stored-normal` | set_exotic_flat_fees | stored fee_tiers length | 408: ok -> OOM | 125711 | 22946 | no | yes |
| `update-admin-stored-normal` | update_admin | stored fee_tiers length | 408: ok -> OOM | 125278 | 22966 | no | yes |
| `cto-revoke-stored-holders` | admin_cto_sharing_config | stored shareholders length, new_admin None | 86: ok -> OOM | 69686 | 61891 | yes | yes |
| `cto-new-admin-stored-holders` | admin_cto_sharing_config | stored shareholders length, new_admin Some | 85: ok -> OOM | 69850 | 61954 | yes | yes |

- **`claim_social_fee_pda` has two ceilings.** A paying claim fails at stored length 835 with `Return data too large
  (1025 > 1024)`, after the events are emitted, because the handler returns the event. Out of memory comes later, at 2173.
  The non-paying paths reach much further: 31768 for nothing due or rate limited, 31678 for a disabled claim and 31291
  for a wrong authority.
- **The largest legal FeeConfig fits.** `update_fee_config` with 50 stored normal tiers, 50 stored stable tiers and 50
  incoming tiers succeeds, and that family stays `ok` up to 96 stored stable tiers.
- **Where the event is logged first, the OOM comes after it.** In the "event logged" column, `yes` means a `Program data:`
  line appears before the panic, so the handler's `emit!` ran and the allocation failed later in the handler. The
  transaction rolls back either way.

## Differences

| family | x | outcome | original CU | rebuild CU | delta | original panic location | rebuild panic location |
|---|---|---|---|---|---|---|---|
| `get-fees-stored-normal` | 0 | panic, index out of bounds | 4529 | 4545 | +16 | `pump-fees-math/src/lib.rs:49:23` | `programs/pump-fees/pump-fees-math/src/lib.rs:49:23` |
| `get-fees-stored-stable` | 0 | panic, index out of bounds | 4672 | 4688 | +16 | `pump-fees-math/src/lib.rs:49:23` | `programs/pump-fees/pump-fees-math/src/lib.rs:49:23` |
| `get-fees-quote-stored-normal` | 0 | panic, index out of bounds | 4616 | 4632 | +16 | `pump-fees-math/src/lib.rs:49:23` | `programs/pump-fees/pump-fees-math/src/lib.rs:49:23` |

All three are the same point: an empty tier list reaching the index at `pump-fees-math/src/lib.rs:49:23`. The rebuild's
panic message carries a longer source path, and the panic path costs 16 CU more. That is the only log difference, and it
matches the difference already reported in `pump-fees-tier-lookup-cost-20261030`. It is not a heap effect. The next point (one
stored tier) matches on both images.

## Limits

- Long ranges use a grid, so an outcome band narrower than a grid gap and bounded by the same class on both sides would
  not be seen. Short ranges have no such gap.
- `update_fee_shares*` was measured for incoming `Vec<Shareholder>` only, with no accounts. Stored shareholder lengths
  were measured on `admin_cto_sharing_config`, which needs no CPI.
- A LiteSVM run shows the heap behaviour of these two images under the bundled runtime, not a cluster-specific result.

## Images

- Original: `evidence/original/pump_fees/deployed.so`, sha256 `4f2955d0f6b40cc9ff7daa18ccad7d19119ba1249759f4e7e3bb691beee6b35e`
- Rebuild: sha256 `7a14f41440c60ac6e95053e9fdc712376a1eac3447ec2de6fa29b1b6ec654900`, built with `scripts/build_partial_candidate.py` (platform-tools v1.44, cargo-build-sbf
  2.1.21) from source tree `bd2409408730976e376f30580a2926f44e14f006`, repository commit
  `e2f999e1fd9150c48b4dc8c6c1838f980da8c6b1`.

## Reproduce

From the repository root:

```
python3 research/pump-fees-heap-ceiling-boundaries-20261030/producer.py --root . \
  --images '{"original": "evidence/original/pump_fees/deployed.so", "candidate": "<candidate.so>"}' \
  --out research/pump-fees-heap-ceiling-boundaries-20261030
cd research/pump-fees-heap-ceiling-boundaries-20261030
python3 verify.py --images '{"original": "../../evidence/original/pump_fees/deployed.so", "candidate": "<candidate.so>"}'
```

`verify.py` needs only the packet files and the two images. It checks the image sha256 values against the report,
replays every family on both images, requires byte-equal receipts and report, requires equal edges, and allows no CU or
log difference other than the +16 CU empty-list panic at x = 0. It exits 0 on success and 1 on any difference.

## Files

- `producer.py`: family definitions, fixtures, scan
- `verify.py`: replay and checks
- `runtime/receipts.jsonl.gz`: per-family scans for each image
- `runtime/report.json.gz`: per-family summary
- `MANIFEST.json`: sha256 and size of every file
