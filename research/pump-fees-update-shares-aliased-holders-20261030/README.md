# Pump Fees update_fee_shares with aliased shareholders, original vs rebuild

## Problem

`update_fee_shares` pays the stored shareholders through a CPI to pump `distribute_creator_fees`, then writes a new
shareholder list. A shareholder is an arbitrary key, so it can equal an account the instruction already passes:
`sharing_config`, the creator vault, the update authority and so on. The same key then fills two slots of the CPI, one
of them a remaining account chosen from the stored list.

Earlier packets on this handler vary the list contents, executable holders and routes. Apart from executable program
ids, their holders are separate accounts. This packet measures the non-executable aliases, and repeated keys in the
stored list.

## Method

35 cases and 97 steps on `update_fee_shares` v1 with the native route. Each case has a fresh LiteSVM per
image, and up to three steps:

- `u1`: `update_fee_shares` with the new list. This is the measured step.
- `d2`: fund the creator vault with 10,000,000 lamports, then pump `distribute_creator_fees` with the new list.
- `u3`: a second `update_fee_shares`.

`u1` runs with 10,000,000 lamports in the vault above the rent floor unless the case says otherwise. Only the pump_fees
image is swapped. pump and pump_amm are the original deployed images on both sides, used as CPI dependencies.

Compared per step: transaction hash, error, full logs, decoded events, lamport changes, owner, length and data hash of
the watched accounts, the decoded `SharingConfig`, and compute units.

Stored lists are written directly into a synthetic `SharingConfig`, so the `old-*` cases include lists that
`update_fee_shares` itself would refuse, such as repeated keys.

## Result

**Original and rebuild match in all 35 cases and 97 steps, including compute units.** No case differs.

| case | setup | u1 (both images) | u1 CU | u1 lamport changes | d2 lamport changes |
|---|---|---|---|---|---|
| `control-two-holders` | two plain holders | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | J +10000000 |
| `control-new-list` | new list with one plain holder, then the follow-up steps | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | C +10000000 |
| `old-holder-sc` | stored holder = sharing_config | ok | 126388 | A +5000000, SC +5000000, pump_creator_vault -10000000, sharing_config +5000000 | J +10000000 |
| `old-holder-va` | stored holder = pump_creator_vault | ok | 126386 | A +5000000, VA -5000000, pump_creator_vault -5000000 | J +15000000, VA -5000000, pump_creator_vault -5000000 |
| `old-holder-cv` | stored holder = bonding_curve | ok | 126354 | A +5000000, CV +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-gl` | stored holder = pump Global | ok | 126719 | A +5000000, GL +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-mi` | stored holder = mint | ok | 126326 | A +5000000, MI +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-au` | stored holder = update authority | ok | 126714 | A +5000000, AU +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-py` | stored holder = transaction fee payer | ok | 126878 | A +5000000, PY +4990000, pump_creator_vault -10000000 | J +10000000, PY -10005000 |
| `old-holder-ev` | stored holder = pump_fees event authority | ok | 126718 | A +5000000, EV +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-pe` | stored holder = pump event authority | ok | 126469 | A +5000000, PE +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-aa` | stored holder = AMM creator vault authority | ok | 126720 | A +5000000, AA +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-ws` | stored holder = WSOL mint | ok | 126715 | A +5000000, WS +5000000, pump_creator_vault -10000000 | J +10000000 |
| `old-holder-sc-sole` | only stored holder = sharing_config | ok | 121972 | SC +10000000, pump_creator_vault -10000000, sharing_config +10000000 | J +10000000 |
| `old-holder-va-sole` | only stored holder = pump_creator_vault | ok | 121970 | none | J +20000000, VA -10000000, pump_creator_vault -10000000 |
| `old-holder-sc-and-va` | stored holders = sharing_config and pump_creator_vault | ok | 125919 | SC +5000000, VA -5000000, pump_creator_vault -5000000, sharing_config +5000000 | J +15000000, VA -5000000, pump_creator_vault -5000000 |
| `old-holder-sc-empty-vault` | stored holder = sharing_config, vault at the rent floor | ok | 115868 | none | J +10000000 |
| `old-holder-va-empty-vault` | stored holder = pump_creator_vault, vault at the rent floor | ok | 115900 | none | J +10000000 |
| `new-holder-sc` | new list = sharing_config | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | SC +10000000, sharing_config +10000000 |
| `new-holder-va` | new list = pump_creator_vault | ok | 126883 | A +5000000, B +5000000, VA -10000000, pump_creator_vault -10000000 | VA +10000000, pump_creator_vault +10000000 |
| `new-holder-cv` | new list = bonding_curve | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | CV +10000000 |
| `new-holder-gl` | new list = pump Global | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | GL +10000000 |
| `new-holder-mi` | new list = mint | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | MI +10000000 |
| `new-holder-au` | new list = update authority | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | AU +10000000 |
| `new-holder-py` | new list = transaction fee payer | ok | 126883 | A +5000000, B +5000000, PY -10000, pump_creator_vault -10000000 | PY -5000 |
| `new-holder-ev` | new list = pump_fees event authority | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | EV +10000000 |
| `new-holder-pe` | new list = pump event authority | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | PE +10000000 |
| `new-holder-aa` | new list = AMM creator vault authority | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | AA +10000000 |
| `new-holder-ws` | new list = WSOL mint | ok | 126883 | A +5000000, B +5000000, pump_creator_vault -10000000 | WS +10000000 |
| `old-duplicate-key` | stored list repeats one key | ok | 126529 | A +10000000, pump_creator_vault -10000000 | J +10000000 |
| `old-duplicate-key-three` | stored list repeats one key among three | ok | 131178 | A +7500000, B +2500000, pump_creator_vault -10000000 | J +10000000 |
| `new-duplicate-key` | new list repeats one key | DuplicateShareholder | 117655 | none | not run |
| `remaining-repeats-first` | remaining accounts repeat the first holder | ShareholderAccountMismatch | 64642 | none | not run |
| `remaining-sc-in-holder-slot` | remaining slot of B holds sharing_config | ShareholderAccountMismatch | 64590 | none | not run |
| `remaining-va-in-holder-slot` | remaining slot of B holds pump_creator_vault | ShareholderAccountMismatch | 64694 | none | not run |

`u3` ran after every successful `u1` and returned `SharingConfigAdminRevoked` (6009) in all 31 of those cases, the
same as in the controls, so it adds no aliasing result beyond confirming that the list and flag stay equal on both
images.

`A`, `B`, `J` and `C` are plain holder keys. `sharing_config` and `SC` are one account listed under two labels, as are
`pump_creator_vault` and `VA`. `PY` figures include the transaction fee.

## What the aliased paths show

- **A holder equal to `sharing_config` is paid and the handler still succeeds.** `old-holder-sc` adds 5000000
  lamports to the account pump_fees is holding as a typed `Account`, and the handler's write-back at exit works on both
  images.
- **A holder equal to the creator vault keeps its own share in the vault.** `old-holder-va` moves only A's 5,000,000 out,
  and `d2` then pays J 15,000,000: the 10,000,000 funded plus the 5,000,000 left behind. `old-holder-va-sole` moves
  nothing in `u1`.
- **An empty vault returns ok with no payout.** Aliased or not, `old-holder-sc-empty-vault` and
  `old-holder-va-empty-vault` log the minimum-balance message and leave lamports alone.
- **Repeated keys in a stored list are paid per entry.** `old-duplicate-key` pays A 10,000,000 and `old-duplicate-key-three`
  pays A 7,500,000 and B 2,500,000. `u1` does not reject a stored repeat. A repeat in the new list returns
  `DuplicateShareholder` at 117655 CU.
- **The remaining-account check runs on key equality.** Passing a repeated or aliased key in another holder's slot returns
  `ShareholderAccountMismatch` before the CPI.
- **CU moves slightly with the alias.** `u1` ranges from 126326 to 126878 CU across the two-holder cases, equal on
  both images in each case.

## Limits

- `update_fee_shares_v2`, the token-quote routes and the graduated AMM route are not included.
- Aliases are tried one key at a time, except `old-holder-sc-and-va`.

## Images

- Original: `evidence/original/pump_fees/deployed.so`, sha256 `4f2955d0f6b40cc9ff7daa18ccad7d19119ba1249759f4e7e3bb691beee6b35e`
- Rebuild: sha256 `7a14f41440c60ac6e95053e9fdc712376a1eac3447ec2de6fa29b1b6ec654900`, built with `scripts/build_partial_candidate.py` (platform-tools v1.44, cargo-build-sbf
  2.1.21) from source tree `bd2409408730976e376f30580a2926f44e14f006`, repository commit
  `e2f999e1fd9150c48b4dc8c6c1838f980da8c6b1`.
- CPI dependencies, same on both sides: `evidence/original/pump/deployed.so` and
  `evidence/original/pump_amm/deployed.so`, sha256 values in `runtime/report.json.gz`.

## Reproduce

From the repository root:

```
python3 research/pump-fees-update-shares-aliased-holders-20261030/producer.py --root . \
  --images '{"original": "evidence/original/pump_fees/deployed.so", "candidate": "<candidate.so>"}' \
  --out research/pump-fees-update-shares-aliased-holders-20261030
cd research/pump-fees-update-shares-aliased-holders-20261030
python3 verify.py --images '{"original": "../../evidence/original/pump_fees/deployed.so", "candidate": "<candidate.so>"}'
```

`verify.py` needs the packet files, the two images, and the pump and pump_amm images found next to the original image.
It checks all four sha256 values against the report, replays every case on both images, requires byte-equal receipts
and report, and allows no difference between the images. It exits 0 on success and 1 on any difference.

## Files

- `producer.py`: fixtures, cases, comparison
- `verify.py`: replay and checks
- `runtime/receipts.jsonl.gz`: per-step results for each image, with full logs
- `runtime/report.json.gz`: per-case summary
- `MANIFEST.json`: sha256 and size of every file
