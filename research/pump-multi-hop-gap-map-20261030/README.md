# Pump Main multi_hop_curve_swap: map of the original-vs-rebuild CU gap by error site and route shape

## Problem

`multi_hop_curve_swap::swap_hop` (original window `0x5b3b0`, 18,584 bytes) is an unmatched Pump Main window with low
similarity in the reconstruction table (0.158). Behavior matches in the existing packets. CU gaps here range from -9 to
+119, and most of that range is error-log cost, which hides where the handler code differs.

## Method

The 60 synthetic cases of `pump-multi-hop-curve-swap-boundaries-20261030`, rerun on the current rebuild. The instruction is sent
directly with signature verification off, as in that packet.

A failing case stops at a known source line. This packet subtracts the cost of its AnchorError line, using the rule measured
in `pump-anchor-error-format-capacity-cu-20261030`:

```
remainder = gap - [(L_orig - L_rebuild) + 104 if L_rebuild <= 142 < L_orig]
```

The remainder is the instruction-count difference accumulated from the entrypoint to that line on that path.

| Image | sha256 | Bytes |
| --- | --- | ---: |
| original | `7a19affaa2c6187e04a5fe0ea298cee81fa5eb8c24cfcc30d85f615e89f7b02d` | 10,485,715 |
| rebuild | `ae713165a56752f7e1c6153137842e2b145885180b5c71e21a342afed45bd44b` | 1,934,928 |

The rebuild comes from `scripts/build_partial_candidate.py` with platform-tools v1.44 / cargo-build-sbf 2.1.21, source
tree `9e5d2900ed30981d5766fb101ef120ee198161be`.

## Results

Behavior matched in 60/60 cases. CU and logs were equal in 5/60.

### Failing sites

| File | Line | Error | L orig / rebuild | Gap | Log cost | Remainder | Cases |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| `multi_hop_curve_swap.rs` | 208 | BuyZeroAmount | 147 / 133 | +118 | 118 | +0 | `pre/amount-zero` |
| `multi_hop_curve_swap.rs` | 214 | NotEnoughRemainingAccounts | 174 / 160 | +14 | 14 | +0 | `pre/remaining-0`, `pre/remaining-4`, `pre/remaining-6` |
| `multi_hop_curve_swap.rs` | 218 | MultiHopHopFeesMismatch | 241 / 227 | +14 | 14 | +0 | `pre/hop-fees-empty`, `pre/hop-fees-2-for-1`, `pre/hop-fee-4` |
| `multi_hop_curve_swap.rs` | 262 | MultiHopDiscontinuousPath | 210 / 196 | +10 | 14 | -4 | `hop/destination-mint-wrong-sell` |
| `multi_hop_curve_swap.rs` | 369 | ConstraintSeeds | 165 / 151 | +13 | 14 | -1 | `hop/base-ata-wrong` |
| `multi_hop_curve_swap.rs` | 369 | ConstraintSeeds | 165 / 151 | +16 | 14 | +2 | `hop/quote-ata-wrong` |
| `multi_hop_curve_swap.rs` | 484 | MultiHopMayhemCurveNotSupported | 221 / 207 | +11 | 14 | -3 | `hop/mayhem` |
| `multi_hop_curve_swap.rs` | 546 | MultiHopDiscontinuousPath | 210 / 196 | +14 | 14 | +0 | `route/discontinuous` |
| `multi_hop_curve_swap.rs` | 546 | MultiHopDiscontinuousPath | 210 / 196 | +19 | 14 | +5 | `hop/source-mint-unrelated` |
| `multi_hop_curve_swap.rs` | 599 | NotEnoughTokensToBuy | 163 / 149 | +12 | 14 | -2 | `buy/native-cross-whitelist` |
| `multi_hop_curve_swap.rs` | 686 | SellZeroAmount | 149 / 135 | +117 | 118 | -1 | `sell/native-1-unit` |
| `fee.rs` | 162 | FeeTiersEmpty | 154 / 140 | +113 | 118 | -5 | `ctx/fee-config-tiers-empty` |
| `fee.rs` | 183 | FeeConfigTooShort | 182 / 168 | +9 | 14 | -5 | `ctx/fee-config-len-2511`, `ctx/fee-config-len-2511-flags-0` |
| `lib.rs` | 1884 | BuybackFeeRecipientNotAuthorized | 171 / 157 | +15 | 14 | +1 | `hop/buyback-unlisted-ata` |
| `lib.rs` | 2535 | Overflow | 119 / 105 | +13 | 14 | -1 | `sell/native-above-rqr` |
| `lib.rs` | 2554 | Overflow | 119 / 105 | +15 | 14 | +1 | `acc/creator-fee-max` |
| `trade_v3.rs` | 149 | BondingCurveComplete | 193 / 179 | +13 | 14 | -1 | `hop/complete` |
| `trade_v3.rs` | 150 | CashbackCoinNotSupported | 195 / 181 | +13 | 14 | -1 | `hop/cashback-flag-2` |
| `trade_v3.rs` | 172 | AccountTypeNotSupported | 156 / 142 | +119 | 118 | +1 | `hop/buyback-wallet-flag-1` |
| `trade_v3.rs` | 180 | MintDoesNotMatchBondingCurve | 177 / 163 | +10 | 14 | -4 | `route/sol-a-b-flags-31` |
| `trade_v3.rs` | 180 | MintDoesNotMatchBondingCurve | 177 / 163 | +15 | 14 | +1 | `spl/buy-flag-1-wsol-buyback` |
| `trade_v3.rs` | 317 | BuyNotEnoughSolToCoverFees | 171 / 157 | +9 | 14 | -5 | `buy/native-1-lamport` |
| `trade_v3.rs` | 506 | NotEnoughTokensToBuy | 151 / 137 | +115 | 118 | -3 | `buy/native-cross-pool-base-0` |

- The three pre-loop sites (`multi_hop_curve_swap.rs` lines 208..218, 7 cases) all have a remainder of 0, so nothing differs on the
  path before the first hop in these cases.
- After those sites, remainders stay between -5 and +5. The gaps of +113..+119 in this table are the 104-CU log term plus
  path bytes, and they leave -5..+1 once it is removed.
- `FeeConfigTooShort` and `FeeTiersEmpty` both sit at -5, at two lines of `fee.rs`, so a difference of -5 is already
  present at the fee read.

### Success paths, by route shape

| Gap | Shape | Cases |
| ---: | --- | ---: |
| -9 | two hops | 4 |
| -8 | two hops | 1 |
| -6 | SPL quote | 1 |
| -4 | SPL quote | 1 |
| -4 | one sell hop | 4 |
| -3 | one buy hop | 10 |
| -3 | two hops, second crosses | 1 |
| +2 | native crossing into post-complete | 2 |

Fee flags do not move the gap: `buy/native-flag-0..3` are all -3 and `sell/native-flag-0..3` all -4. The gap depends on the route shape.
A second hop takes it from -3/-4 to -8/-9, an SPL quote adds -1 on a buy and -2 on a sell, and crossing into the post-complete
fill moves it +5, in both the one-hop (-3 to +2) and the two-hop (-8 to -3) route.

8 further cases stop at an account constraint or a non-Anchor error and are in `runtime/report.json.gz`, not in these tables.

## Limits

- A remainder is cumulative along one path, and one file's line numbers do not give execution order across files. Rows locate
  spans, not instructions.
- The log-cost term comes from the companion packet's rule. It is applied here, not re-derived.
- This packet locates spans and shapes. It does not name a compiler or source cause.
- All state is synthetic, and on mainnet only `pump_amm` calls this instruction.

## Reproduce

```
python3 producer.py --root <repo> --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}' --out <packet>
python3 verify.py --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}'
```

`verify.py` checks the manifest and image sha256 values, replays all cases on both images, and recomputes the summary, including
the map, from the replay.

## Files

- `producer.py`, `verify.py`
- `runtime/plan.json.gz`: all 60 cases
- `runtime/receipts-upgradeable.jsonl.gz`: per-image receipts
- `runtime/report.json.gz`: summary and `gap_map`
