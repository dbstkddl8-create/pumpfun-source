# pump_amm legacy `buy` / `buy_exact_quote_in` / `sell`: disable flags, recipients, buyback, pool-v2 and cashback routing, and a panic path that costs more in the rebuild

## Question

Legacy trades read their fee destinations from remaining accounts whose positions depend on the fee amounts: an
optional pool-v2 slot, optional cashback slots, then a buyback pair. This packet measures, one instruction at a time,
the check order and each failure of that routing (`instructions/swap/buy.rs`, `sell.rs`, `swap/mod.rs`,
`state/global_config.rs`), plus disable flags, mayhem recipients, the whitelist, the per-pool creator bps override
and pool accounts shorter than 287 bytes.

The main result: behavior is equal, and the two panic cases are the only cases in this packet where the rebuild
costs *more* CU than the original, although its panic message is shorter.

## Images

| image | sha256 |
|---|---|
| original `evidence/original/pump_amm/deployed.so` | `6a7ad34596d83b4c435b32f458a56e718e9f82eb4ad38e4316616d15d24d8ff7` |
| rebuild `<candidate.so>` (`scripts/build_partial_candidate.py`, platform-tools v1.44 / cargo-build-sbf 2.1.21, source tree `755200a0d9fffe6f82a43fb65cc452d164f6e90b`, repo commit `1e04f5b34aa33c53f2b20b4200ba4ba266b4203e`) | `384737bdc6c54cca4330fd5ce15f8c556a40a78afa6a93a69fe47d2b18527ab5` |

## Setup

Same harness as `pump-amm-legacy-trade-arithmetic-boundaries-20261030`: fresh LiteSVM per case, synthetic GlobalConfig
(949 B), Pool (287 B or a shorter legacy length), FeeConfig and GlobalVolumeAccumulator, SPL Token accounts, one
instruction under a 1,400,000 CU limit. The `get_fees_with_quote_mint` CPI lands on a stub that returns the case's bps;
the default is lp 20, protocol 5, creator 30. pump_amm is loaded with a program account plus programdata, because with
the ELF in the program account a nominal `sell` shows 134974 vs 98103 CU, a gap of 36871 equal to
(10485715 - 1267912) / 250 = 36871, billed by the CPI's `data_len / 250` charge (`inline_layout_control` in the report).

## Result

- **Behavior:** original and rebuild agree on error and post-state in 60/60 cases (28 successes,
  32 failures).
- **CU:** 29/60 equal, including all 28 successes. Delta histogram (rebuild minus original): -122: 5, -18: 24, 0: 29, 101: 2.
- **Logs:** exact in 29/60; 60/60 after replacing `programs/pump-amm/src/` with `src/`.

## The +101 panic

`b-buyback-11000-bps` and `s-buyback-11000-bps` use a stored `buyback_basis_points` above 10000, which
`set_buyback_basis_points` refuses (`global_config.rs:306`), so only a directly written account reaches it. Then
`split_buyback_fee` hits `expect("buyback_fee never exceeds protocol_fee")` at `global_config.rs:391`:

| case | CU original | CU rebuild | delta | control |
|---|---:|---:|---:|---:|
| `b-buyback-11000-bps` | 62601 | 62702 | +101 | 62702 |
| `s-buyback-11000-bps` | 51383 | 51484 | +101 | 51484 |

The log line is 18 bytes shorter in the rebuild, yet the rebuild spends 101 CU more. The control below moves only
string references, and with it the original lands exactly on the rebuild's CU, so this delta is also the file-name
string, through `String` growth. The panic message is built with no initial capacity, then grown by doubling. Tracing
that growth (derived from `RawVec` amortized growth, not measured separately):

| step | bytes after step | original capacity | rebuild capacity |
|---|---:|---:|---:|
| `panicked at ` | 12 | 12 | 12 |
| file name | 56 / 38 | 56 | 38 |
| `:` | 57 / 39 | 112 | 76 |
| `391:14:\n` | 65 / 47 | 112 | 76 |
| message | 103 / 85 | 112 | **152** |

The longer original name reaches a capacity that holds the whole line. The rebuild's shorter name needs one more growth.
That matches +101 = -18 (`sol_log`) + 119 (one growth). This path is reachable only with a stored value above the setter's limit.

## Other CU deltas

29 of the 29 AnchorError cases follow the rule from the companion packet: -122 when the rebuild's message fits
the 142-byte initial capacity of anchor-lang's `format!` and the original's does not, otherwise -18. The capacity is
twice the 71 literal bytes in the format string, read from both images (22 + 1 + 14 + 16 + 17 + 1).

| rebuild message bytes | original message bytes | CU delta | predicted | cases |
|---:|---:|---:|---:|---:|
| 128 | 146 | -122 | -122 | 4 |
| 131 | 149 | -122 | -122 | 1 |
| 158 | 176 | -18 | -18 | 3 |
| 160 | 178 | -18 | -18 | 6 |
| 167 | 185 | -18 | -18 | 3 |
| 172 | 190 | -18 | -18 | 4 |
| 184 | 202 | -18 | -18 | 4 |
| 185 | 203 | -18 | -18 | 1 |
| 187 | 205 | -18 | -18 | 1 |
| 192 | 210 | -18 | -18 | 2 |

**Control.** A copy of the original with only its path strings moved (245 code references and 41 panic `Location`
records, sha256 `7e9124130f1db8783911add3d3ff5987a2081e941756a3419b7b0107b749e271`) equals the rebuild in CU 60/60, logs 60/60, error and state 60/60.

## Behaviors worth noting (identical in both images)

- Check order: disable flag, then protocol fee recipient, then zero amounts (`b-disabled-before-*`,
  `b-recipient-before-zero-amount`). Only bit 8 stops buys and only bit 16 stops sells.
- The buyback pair is required even when `buyback_bps` is 0 (`b-buyback-accounts-missing-0-bps`), but the ATA is created
  only if the floored amount is above 0 (`b-buyback-ata-absent-floor-zero`).
- The buyback pair index moves with the fee amount, not with configuration: with no coin creator the pair sits at index 0,
  so passing the pool-v2 slot anyway fails with `BuybackFeeRecipientNotAuthorized` (`b-no-coin-creator-extra-v2`).
- Mayhem pools take no buyback split, so an absent buyback ATA stays absent (`b-mayhem-no-split`). A `is_mayhem_mode` byte of 2 fails
  in Borsh before any handler check, with no file name, so its delta is 0.
- The missing-buyback failure comes after the base, quote, protocol and creator transfers, at 83693 CU against 37414 for a
  disabled buy, and those transfers roll back.
- Pools of 279 and 243 bytes are topped up and reallocated to 287 in both images: +624 CU on `buy` (`b-pool-len-279`) and
  +467 CU on `sell` (`s-pool-len-243`) against the nominal runs.

## Cases

### disable

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-disabled` | buy | DisabledBuy | instructions/swap/buy.rs:317 | 37414 | 37292 | -122 | yes |
| `x-disabled` | buy_exact_quote_in | DisabledBuy | instructions/swap/buy.rs:625 | 37417 | 37295 | -122 | yes |
| `s-disabled` | sell | DisabledSell | instructions/swap/sell.rs:101 | 26208 | 26086 | -122 | yes |
| `b-sell-flag-only` | buy | ok |  | 105331 | 105331 | +0 | yes |
| `s-buy-flag-only` | sell | ok |  | 93032 | 93032 | +0 | yes |
| `b-other-flag-bits` | buy | ok |  | 105331 | 105331 | +0 | yes |
| `b-disabled-before-zero-amount` | buy | DisabledBuy | instructions/swap/buy.rs:317 | 37414 | 37292 | -122 | yes |
| `b-disabled-before-recipient` | buy | DisabledBuy | instructions/swap/buy.rs:317 | 38914 | 38792 | -122 | yes |

### recipient

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-recipient-7` | buy | ok |  | 106785 | 106785 | +0 | yes |
| `b-recipient-stranger` | buy | InvalidProtocolFeeRecipient | instructions/swap/mod.rs:164 | 39182 | 39164 | -18 | yes |
| `x-recipient-stranger` | buy_exact_quote_in | InvalidProtocolFeeRecipient | instructions/swap/mod.rs:164 | 39185 | 39167 | -18 | yes |
| `s-recipient-stranger` | sell | InvalidProtocolFeeRecipient | instructions/swap/mod.rs:164 | 27972 | 27954 | -18 | yes |
| `b-recipient-before-zero-amount` | buy | InvalidProtocolFeeRecipient | instructions/swap/mod.rs:164 | 39182 | 39164 | -18 | yes |
| `b-mayhem-reserved` | buy | ok |  | 97621 | 97621 | +0 | yes |
| `s-mayhem-reserved-list-6` | sell | ok |  | 86983 | 86983 | +0 | yes |
| `b-mayhem-normal-recipient` | buy | InvalidProtocolFeeRecipient | instructions/swap/mod.rs:164 | 37772 | 37754 | -18 | yes |
| `b-reserved-nonmayhem` | buy | InvalidProtocolFeeRecipient | instructions/swap/mod.rs:164 | 39182 | 39164 | -18 | yes |
| `b-mayhem-byte-2` | buy | BorshIoError("Invalid bool representation: 2") |  | 11446 | 11446 | +0 | yes |
| `b-recipient-ata-created` | buy | ok |  | 130909 | 130909 | +0 | yes |
| `s-vault-ata-created` | sell | ok |  | 121610 | 121610 | +0 | yes |

### buyback

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-buyback-0-bps` | buy | ok |  | 96506 | 96506 | +0 | yes |
| `b-buyback-10000-bps` | buy | ok |  | 96576 | 96576 | +0 | yes |
| `s-buyback-10000-bps` | sell | ok |  | 84276 | 84276 | +0 | yes |
| `b-buyback-floor-zero` | buy | ok |  | 96534 | 96534 | +0 | yes |
| `b-buyback-accounts-missing` | buy | BuybackFeeRecipientMissing | instructions/swap/buy.rs:116 | 83693 | 83675 | -18 | yes |
| `b-buyback-accounts-missing-0-bps` | buy | BuybackFeeRecipientMissing | instructions/swap/buy.rs:116 | 83691 | 83673 | -18 | yes |
| `s-buyback-owner-only` | sell | BuybackFeeRecipientMissing | instructions/swap/buy.rs:121 | 72900 | 72882 | -18 | yes |
| `b-buyback-unauthorized` | buy | BuybackFeeRecipientNotAuthorized | state/global_config.rs:326 | 84536 | 84518 | -18 | yes |
| `s-buyback-unauthorized` | sell | BuybackFeeRecipientNotAuthorized | state/global_config.rs:326 | 73483 | 73465 | -18 | yes |
| `b-buyback-default-owner` | buy | BuybackFeeRecipientNotAuthorized | state/global_config.rs:321 | 84646 | 84628 | -18 | yes |
| `b-buyback-index-7` | buy | ok |  | 107013 | 107013 | +0 | yes |
| `b-buyback-ata-created` | buy | ok |  | 130903 | 130903 | +0 | yes |
| `s-buyback-ata-created` | sell | ok |  | 118604 | 118604 | +0 | yes |
| `b-buyback-ata-absent-floor-zero` | buy | ok |  | 96534 | 96534 | +0 | yes |
| `b-mayhem-no-split` | buy | ok |  | 97621 | 97621 | +0 | yes |
| `b-buyback-11000-bps` | buy | panic |  | 62601 | 62702 | +101 | yes |
| `s-buyback-11000-bps` | sell | panic |  | 51383 | 51484 | +101 | yes |

### pool-v2

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-pool-v2-wrong` | buy | InvalidPoolV2 | instructions/swap/sell.rs:526 | 75407 | 75389 | -18 | yes |
| `s-pool-v2-wrong` | sell | InvalidPoolV2 | instructions/swap/sell.rs:526 | 64253 | 64235 | -18 | yes |
| `b-pool-v2-missing` | buy | InvalidPoolV2 | instructions/swap/sell.rs:520 | 71549 | 71531 | -18 | yes |
| `b-no-coin-creator` | buy | ok |  | 95874 | 95874 | +0 | yes |
| `b-no-coin-creator-extra-v2` | buy | BuybackFeeRecipientNotAuthorized | state/global_config.rs:326 | 75337 | 75319 | -18 | yes |

### cashback

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-cashback` | buy | ok |  | 138273 | 138273 | +0 | yes |
| `x-cashback` | buy_exact_quote_in | ok |  | 140005 | 140005 | +0 | yes |
| `s-cashback` | sell | ok |  | 136574 | 136574 | +0 | yes |
| `b-cashback-ata-missing` | buy | MissingCashbackAccounts | instructions/swap/buy.rs:44 | 71577 | 71559 | -18 | yes |
| `b-cashback-ata-wrong` | buy | InvalidCashbackAccumulatorAta | instructions/swap/buy.rs:54 | 75799 | 75781 | -18 | yes |
| `b-cashback-ata-readonly` | buy | InvalidCashbackAccumulatorAta | instructions/swap/buy.rs:57 | 75814 | 75796 | -18 | yes |
| `s-cashback-uva-missing` | sell | MissingCashbackAccounts | instructions/swap/sell.rs:383 | 60686 | 60668 | -18 | yes |
| `s-cashback-uva-wrong` | sell | InvalidCashbackAccumulator | instructions/swap/sell.rs:392 | 64829 | 64811 | -18 | yes |
| `s-cashback-uva-readonly` | sell | InvalidCashbackAccumulator | instructions/swap/sell.rs:395 | 64845 | 64827 | -18 | yes |
| `s-cashback-uva-bad-disc` | sell | InvalidCashbackAccumulator | instructions/swap/sell.rs:448 | 64917 | 64899 | -18 | yes |
| `s-cashback-uva-foreign-owner` | sell | InvalidCashbackAccumulator | instructions/swap/sell.rs:444 | 64883 | 64865 | -18 | yes |
| `b-cashback-zero-creator-bps` | buy | ok |  | 93177 | 93177 | +0 | yes |

### overrides

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-whitelist` | buy | ok |  | 75591 | 75591 | +0 | yes |
| `s-whitelist` | sell | ok |  | 63163 | 63163 | +0 | yes |
| `b-creator-bps-override` | buy | ok |  | 105335 | 105335 | +0 | yes |
| `b-creator-bps-config-off` | buy | ok |  | 105331 | 105331 | +0 | yes |

### pool-length

| case | ix | original result | site (rebuild path) | CU original | CU rebuild | delta | match |
|---|---|---|---|---:|---:|---:|---|
| `b-pool-len-279` | buy | ok |  | 105955 | 105955 | +0 | yes |
| `s-pool-len-243` | sell | ok |  | 93499 | 93499 | +0 | yes |

## Reproduce

```
python3 producer.py --root <repo> --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}' --out <this folder>
python3 verify.py --images '{"original": "<deployed.so>", "candidate": "<candidate.so>"}'
```

`verify.py` checks both image hashes against `runtime/report.json.gz`, re-runs every case and requires byte-identical
receipts and report. `producer.py` needs `solders` 0.27.1 only and uses no network.

## Limits

State is synthetic and pump_fees is a stub in every run, so fee tiers are not tested. Token-2022 quote mints are not in
this packet.
