# pump_amm legacy `buy` / `buy_exact_quote_in` / `sell`: curve, fee and reserve arithmetic boundaries, and what sets the CU delta on error paths

## Question

The existing packets reach `pump_amm` trades through `multi_hop_swap` or as one step of a chain.
The legacy single-hop handlers (`programs/pump-amm/src/instructions/swap/buy.rs`, `sell.rs`) were
not measured at their numeric edges. This packet drives them one instruction at a time:

1. `quote_for_base`, `quote_for_sell` and `base_for_quote` at the ends of the reserve range
   (`curve/constant_product.rs`), and the ceiling fee in `fee()` (`curve/fees.rs:29`);
2. every checked-add site that sums curve and fees (`buy.rs:385-395`, `:708-712`) and every
   subtraction site in `sell.rs:165-183`;
3. the `buy_exact_quote_in` estimate and its two downward adjustments (`buy.rs:668-755`) with
   spendable amounts of 1, 2, 3, 4 and the smallest amount that buys any base;
4. the real-versus-virtual reserve checks (`available_quote_reserves`, `effective_quote_reserves`,
   `InsufficientRealQuoteReserves`), each with exact and off-by-one inputs from a Python model.

Behavior is equal in every case. The new result is the cause of the CU delta on error paths, which
explains the `-104` part of the `-122` delta reported in `pump-amm-liquidity-rounding-boundaries-20261030`.

## Images

| image | sha256 |
|---|---|
| original `evidence/original/pump_amm/deployed.so` | `6a7ad34596d83b4c435b32f458a56e718e9f82eb4ad38e4316616d15d24d8ff7` |
| rebuild `<candidate.so>` (`scripts/build_partial_candidate.py`, platform-tools v1.44 / cargo-build-sbf 2.1.21, source tree `755200a0d9fffe6f82a43fb65cc452d164f6e90b`, repo commit `1e04f5b34aa33c53f2b20b4200ba4ba266b4203e`) | `384737bdc6c54cca4330fd5ce15f8c556a40a78afa6a93a69fe47d2b18527ab5` |

## Setup

Each case starts from a fresh LiteSVM with a synthetic 949-byte GlobalConfig, a 287-byte Pool (written
directly, so reserves, accrued fees and `virtual_quote_reserves` are inputs), a FeeConfig, a
GlobalVolumeAccumulator and SPL Token accounts, and sends one instruction with a 1,400,000 CU limit.

- **Fee CPI.** `get_fees_with_quote_mint` lands on a small stub at the pump_fees address that returns the
  case's `(lp, protocol, creator)` bps as return data, in every run. Fee bps are therefore an input, and
  values the real fee program would not return (10001 bps, 2^31-1 bps) are used on purpose to reach the
  subtraction and truncation sites. `pump_fees` itself is not under test here.
- **Program layout.** pump_amm is loaded the mainnet way: program account plus programdata. This matters.
  The program account is an account of the fee CPI, and CPI bills `data_len / 250`. With LiteSVM's
  `add_program` the ELF sits in the program account, and one nominal `sell` then shows
  134974 (original) vs 98103 (rebuild) CU, a gap of 36871 that equals the ELF size gap
  (10485715 - 1267912) / 250 = 36871. That gap is a harness artifact, not a program difference. It is
  recorded in `inline_layout_control` in the report and is absent from every case below.

The Python model in `producer.py` (`buy_total`, `exact_plan`, `sell_out`) picks the boundary inputs.
Pools with zero effective quote reserves that succeed are left out of this packet.

## Result

- **Behavior:** original and rebuild agree on error and post-state in 60/60 cases
  (15 successes, 45 failures).
- **CU:** 19/60 equal, including all 15 successes. Delta histogram (rebuild minus
  original): -122: 11, -18: 28, -17: 2, 0: 19.
- **Logs:** exact in 19/60; 60/60 after replacing `programs/pump-amm/src/`
  with `src/`. No other log text differs.

## Cause of the CU deltas

| delta | condition | location |
|---|---|---|
| -18 | error path that logs a file name | `file!()` is `programs/pump-amm/src/...` in the original and `src/...` in the rebuild: 18 bytes fewer in `sol_log` |
| -122 | the same, and the rebuild's message fits the initial `String` capacity while the original's does not | one `String` growth skipped in the rebuild's `format!` |
| -17 | `sell.rs:171`, messages longer than twice the capacity | -18 plus 1 CU; length-dependent (the control reproduces it), not attributed further |

`programs/pump-amm/Cargo.toml` has its own `[workspace]`, so the rebuild's `file!()` is crate-relative.

The AnchorError line is built by one `format!` in anchor-lang. Its literal pieces, read from the
`fmt::Arguments` piece table in both images, have lengths 22 + 1 + 14 + 16 + 17 + 1 = 71 bytes, so
`fmt::Arguments::estimated_capacity` gives 142. A message of at most 142 bytes never grows the buffer.
The rule **-122 if `rebuild_len <= 142 < original_len`, else -18** matches 39 of the 41 AnchorError
cases; the only misses are the 2 `sell.rs:171` cases at -17.

| rebuild message bytes | original message bytes | CU delta | predicted | cases |
|---:|---:|---:|---:|---:|
| 110 | 128 | -18 | -18 | 1 |
| 111 | 129 | -18 | -18 | 7 |
| 114 | 132 | -18 | -18 | 2 |
| 122 | 140 | -18 | -18 | 4 |
| 123 | 141 | -18 | -18 | 6 |
| 126 | 144 | -122 | -122 | 2 |
| 134 | 152 | -122 | -122 | 3 |
| 135 | 153 | -122 | -122 | 1 |
| 136 | 154 | -122 | -122 | 2 |
| 138 | 156 | -122 | -122 | 1 |
| 139 | 157 | -122 | -122 | 2 |
| 172 | 190 | -18 | -18 | 3 |
| 187 | 205 | -18 | -18 | 1 |
| 209 | 227 | -18 | -18 | 4 |
| 290 | 308 | -17 | -18 | 2 |

So the `-104` is not tied to `map_err`/`ok_or_else` closures or to any error site: it follows message length
only. Message length comes from the file path, line digits and the error name and text. The measured data
brackets the threshold (no skipped growth at 123/141 bytes, a skipped growth at 126/144), consistent with 142.

**Control.** A copy of the original with only the path strings moved (245 code references plus 41
panic `Location` records, each 18 bytes later and 18 shorter, sha256 `7e9124130f1db8783911add3d3ff5987a2081e941756a3419b7b0107b749e271`) gives CU equal to the rebuild in
60/60, logs equal in 60/60, error and state equal in 60/60. The whole delta is
therefore the file-name string. Nothing in the handlers differs in cost here.

## Behaviors worth noting (identical in both images)

- `buy` with `base_amount_out == reserve` is `DivisionByZero` from `ceil_div` (`fees.rs:21`), and with zero quote
  reserves too it is `Overflow` (`fees.rs:19`, the `checked_sub(1)`). Above the reserve it is
  `BuyMoreBaseAmountThanPoolReserves`.
- `buy_exact_quote_in`: spend 1 fails at the estimate (6039), spend 2 at the first adjustment (6039, logged without
  a file name, so delta 0), spend 3 at `curve > 0` (6040), spend 4 at `base_out >= min` (6040). The first three use
  different code paths for nearly the same input.
- `x-total-sum-overflow` and `x-spend-max` fail in `.ok_or(PumpAmmError::Overflow)` sites, which log no file name, so
  their delta is 0, unlike the `.ok_or_else(|| error!(..))` sites in `buy`.
- `sell` checks `InsufficientRealQuoteReserves` against `quote - lp_fee`, before creator and protocol fees are
  removed (`sell.rs:171`): `s-real-exact` passes with a vault equal to that amount.

## Cases

### buy-curve

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-nominal` | buy | ok |  | 105331 | 105331 | +0 | yes |
| `b-limit-exact` | buy | ok |  | 105331 | 105331 | +0 | yes |
| `b-limit-minus-1` | buy | ExceededSlippage | instructions/swap/buy.rs:405 | 46998 | 46876 | -122 | yes |
| `b-out-1-ceil` | buy | ok |  | 96534 | 96534 | +0 | yes |
| `b-out-reserve-minus-1` | buy | Truncation | curve/constant_product.rs:24 | 38045 | 37923 | -122 | yes |
| `b-out-eq-reserve` | buy | DivisionByZero | curve/fees.rs:21 | 37755 | 37737 | -18 | yes |
| `b-out-reserve-plus-1` | buy | BuyMoreBaseAmountThanPoolReserves | curve/constant_product.rs:21 | 37817 | 37799 | -18 | yes |
| `b-out-max` | buy | BuyMoreBaseAmountThanPoolReserves | curve/constant_product.rs:21 | 37817 | 37799 | -18 | yes |
| `b-zero-out` | buy | ZeroBaseAmount | instructions/swap/buy.rs:326 | 38856 | 38734 | -122 | yes |
| `b-zero-limit` | buy | ZeroQuoteAmount | instructions/swap/buy.rs:327 | 38860 | 38738 | -122 | yes |
| `b-empty-base-reserve` | buy | BuyMoreBaseAmountThanPoolReserves | curve/constant_product.rs:21 | 37817 | 37799 | -18 | yes |
| `b-q-zero-out-eq-reserve` | buy | Overflow | curve/fees.rs:19 | 37737 | 37719 | -18 | yes |

### buy-overflow

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-sum-lp-overflow` | buy | Overflow | instructions/swap/buy.rs:387 | 44682 | 44664 | -18 | yes |
| `b-sum-creator-overflow` | buy | Overflow | instructions/swap/buy.rs:391 | 44948 | 44930 | -18 | yes |
| `b-sum-protocol-overflow` | buy | Overflow | instructions/swap/buy.rs:395 | 44698 | 44680 | -18 | yes |
| `b-fee-truncation` | buy | Truncation | curve/fees.rs:32 | 43926 | 43908 | -18 | yes |
| `b-curve-truncation` | buy | Truncation | curve/constant_product.rs:24 | 38046 | 37924 | -122 | yes |

### buy-reserves

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-accrued-eq-vault` | buy | ok |  | 105330 | 105330 | +0 | yes |
| `b-accrued-exceeds-vault` | buy | Overflow | state/pool.rs:417 | 37609 | 37591 | -18 | yes |
| `b-accrued-sum-overflow` | buy | Overflow | state/pool.rs:408 | 37607 | 37589 | -18 | yes |
| `b-vqr-neg-past-zero` | buy | Overflow | state/pool.rs:440 | 37639 | 37621 | -18 | yes |
| `b-vqr-pos-past-u64` | buy | Overflow | state/pool.rs:440 | 37638 | 37620 | -18 | yes |
| `b-vqr-i128-overflow` | buy | Overflow | state/pool.rs:439 | 37638 | 37620 | -18 | yes |

### exact-estimate

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `x-nominal` | buy_exact_quote_in | ok |  | 107064 | 107064 | +0 | yes |
| `x-min-exact` | buy_exact_quote_in | ok |  | 107064 | 107064 | +0 | yes |
| `x-min-plus-1` | buy_exact_quote_in | BuySlippageBelowMinBaseAmountOut | instructions/swap/buy.rs:776 | 48720 | 48702 | -18 | yes |
| `x-spend-1-estimate-zero` | buy_exact_quote_in | BuyNotEnoughQuoteTokensToCoverFees | instructions/swap/buy.rs:700 | 46723 | 46705 | -18 | yes |
| `x-spend-2-adjust-underflow` | buy_exact_quote_in | BuyNotEnoughQuoteTokensToCoverFees |  | 46236 | 46236 | +0 | yes |
| `x-spend-3-curve-zero` | buy_exact_quote_in | BuySlippageBelowMinBaseAmountOut | instructions/swap/buy.rs:733 | 47760 | 47742 | -18 | yes |
| `x-spend-4-base-zero` | buy_exact_quote_in | BuySlippageBelowMinBaseAmountOut | instructions/swap/buy.rs:776 | 48134 | 48116 | -18 | yes |
| `x-smallest-spend-with-base` | buy_exact_quote_in | ok |  | 98009 | 98009 | +0 | yes |
| `x-below-smallest-spend` | buy_exact_quote_in | BuySlippageBelowMinBaseAmountOut | instructions/swap/buy.rs:776 | 48134 | 48116 | -18 | yes |
| `x-zero-spend` | buy_exact_quote_in | ZeroQuoteAmount | instructions/swap/buy.rs:638 | 38863 | 38741 | -122 | yes |
| `x-zero-min` | buy_exact_quote_in | ZeroBaseAmount | instructions/swap/buy.rs:636 | 38859 | 38737 | -122 | yes |
| `x-all-fees-zero` | buy_exact_quote_in | ok |  | 77053 | 77053 | +0 | yes |
| `x-no-coin-creator` | buy_exact_quote_in | ok |  | 97301 | 97301 | +0 | yes |
| `x-fee-100pct` | buy_exact_quote_in | ok |  | 77309 | 77309 | +0 | yes |
| `x-total-sum-overflow` | buy_exact_quote_in | Overflow |  | 45945 | 45945 | +0 | yes |
| `x-spend-max` | buy_exact_quote_in | Overflow |  | 45906 | 45906 | +0 | yes |
| `x-q-zero-curve-1` | buy_exact_quote_in | DivisionByZero | curve/constant_product.rs:85 | 46335 | 46213 | -122 | yes |
| `x-empty-base-reserve` | buy_exact_quote_in | DivisionByZero | state/pool.rs:386 | 41086 | 41068 | -18 | yes |

### sell-curve

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `s-nominal` | sell | ok |  | 93032 | 93032 | +0 | yes |
| `s-min-exact` | sell | ok |  | 93032 | 93032 | +0 | yes |
| `s-min-plus-1` | sell | ExceededSlippage | instructions/swap/sell.rs:189 | 35627 | 35505 | -122 | yes |
| `s-zero-amount` | sell | ZeroBaseAmount | instructions/swap/sell.rs:110 | 27647 | 27525 | -122 | yes |
| `s-quote-floor-zero` | sell | ok |  | 54405 | 54405 | +0 | yes |
| `s-quote-1-fee-underflow` | sell | Overflow | instructions/swap/sell.rs:179 | 34039 | 34021 | -18 | yes |
| `s-quote-3-user-zero` | sell | ok |  | 75444 | 75444 | +0 | yes |
| `s-quote-3-min-1` | sell | ExceededSlippage | instructions/swap/sell.rs:189 | 35452 | 35330 | -122 | yes |
| `s-lp-exceeds-quote` | sell | Overflow | instructions/swap/sell.rs:167 | 33698 | 33680 | -18 | yes |
| `s-creator-exceeds-quote` | sell | Overflow | instructions/swap/sell.rs:179 | 34007 | 33989 | -18 | yes |
| `s-protocol-exceeds-quote` | sell | Overflow | instructions/swap/sell.rs:183 | 33754 | 33736 | -18 | yes |
| `s-fee-truncation` | sell | Truncation | curve/fees.rs:32 | 32654 | 32636 | -18 | yes |
| `s-empty-base-reserve` | sell | DivisionByZero | state/pool.rs:386 | 29987 | 29969 | -18 | yes |

### sell-reserves

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `s-real-short` | sell | InsufficientRealQuoteReserves | instructions/swap/sell.rs:171 | 35802 | 35785 | -17 | yes |
| `s-real-exact` | sell | ok |  | 93032 | 93032 | +0 | yes |
| `s-real-accrued-short` | sell | InsufficientRealQuoteReserves | instructions/swap/sell.rs:171 | 35802 | 35785 | -17 | yes |
| `s-accrued-exceeds-vault` | sell | Overflow | state/pool.rs:417 | 33979 | 33961 | -18 | yes |
| `s-vqr-neg-past-zero` | sell | Overflow | state/pool.rs:440 | 26390 | 26372 | -18 | yes |
| `s-user-short-of-base` | sell | custom 1 |  | 39241 | 39241 | +0 | yes |

## Reproduce

```
python3 producer.py --root <repo> --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}' --out <this folder>
python3 verify.py --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}'
```

`verify.py` checks both image hashes against `runtime/report.json.gz`, re-runs every case and requires the receipts
and report to be byte-identical. `producer.py` needs `solders` 0.27.1 only and uses no network.

## Limits

State is synthetic: accounts are written directly, so inputs such as 10001 bps or accrued fees above the vault show
how each site behaves, not that production reaches them. The fee stub replaces pump_fees in all runs. Fee routing is in
the companion packet `pump-amm-legacy-trade-fee-routing-20261030`. Token-2022 quote mints are not in this packet.
