# w16a17-cto-stitch16: wave-16 integrator for admin_cto::execute (0x22a10)

Target `0x22a10` `admin_cto::execute` (`programs/pump/src/creator/admin_cto.rs`), pinned at 27,400 B.
Base: main 599891304 (admin_cto.rs as on 1f4e396b5: A6 + ev6): 0.67436, M 2,251, 3,141 slots (`$BASE`, not rebuilt; the
raw-IR capture `m0` reproduces it, `eq_main: true`). Successor of w16a02-cto-faithknobs (#3858) and w16a05-cto-skelsplice
(#3869). Ledger approach `stitch16`, keys `0x22a10-w16-5998913-stitch16-<name>-v1`.

**Result: notes only, no landing.** No composite of the cached library reaches M 2,252 at 27,400 B, and no tie at M 2,251
has fewer positional slots than main (land.py ranks admin_cto by ratio, then slots). The library is now one catalog on the
current main; the splice oracle reproduces every new-main recapture and every built composite tested here byte for byte
(one size miss, explained below). Every lead that is above main alone (g1 +2, crl3/crl2 +1, crl3+g1+t1n +1) sits 16-120 B
over the pin, and the cheapest library repay at each of those sizes costs more than the lead gains.

M is the masked difflib match count of measure.sh: ratio = 2M / (6676 + (bytes - 27400)/8), so +1 M = +0.0003.

## 1. One catalog on the current main (`tools/cat16b.py`, `data/sizeknobs-w16b.json`)

- Every `rx/*/fn.bin` of the w15/w16 lanes within 26-29 KB, deduplicated by bytes (a source-named duplicate is preferred
  over `mp_`/`__ra`/`*ra` oracle names). Round 2 (18:46 PDT): 5,021 paths, 2,174 unique builds, 873 usable source rows.
- Base of each capture: the lane's `res-<sha7>.jsonl` file, else the ledger key's main sha7, else the nearer main by
  instruction-diff size. Known old source (9bd38c7/86e2a6b/9120883/1cc4879) 924, known new (1f4e396/5998913/7e5ba44) 377,
  older sources (90300f9, ed47ac7 and before) 333 (excluded), guessed 579.
  - Two traps: an old capture that already holds one of main's two hunks looks "new" by diff size (w15a30
    `ev_6012345789abc` lacks only A6, and translating it applies ev6 twice); and the w15a01 `F_*` and w15a03 `H_*` rows
    were built on ed47ac7 / 90300f9, so their deltas include older source differences (`F_l2l_cashback` is -8 B there but
    0 B on the current source; `H_hkl2` is 2,248 there while `hkl2` collapses on the current source, 27,288 B, -203).
- Old-source captures are translated onto the new main with the splice oracle, `splice(old main, [new main, capture])`
  (the capture's own local change applied on top of A6+ev6). Captures whose own diff touches the A6/ev6 hunks (old-main
  tokens 1115-1133 and 2425-2495) are flagged and skipped by the screens. Every usable capture is snapshotted into
  `$C/lanes/w16a17-cto-stitch16/tx/` (other lanes overwrite or delete their rx dirs; w16a15's `hOKLD` disappeared mid-run).
- **Validation:** 16 single genes recaptured on 599891304 (section 3) are byte-identical (masked) to their translations,
  g1 included; crl3+t1n, sh_iflet+cu_unwrapcur, sh_iflet+wl_writ_eq and hkl3+lfb5 are byte-identical to the splice of their
  singles. The one miss (L1, 27,408 B against a predicted 27,400 B) used `F_l2l_cashback`, an ed47ac7 capture.
- `data/sizeknobs-w16b.json` (604 rows, round 1): per usable source capture with M >= 2,150 on the new main: bytes/M on
  the new main, base and base sha, provenance, where the bytes land (`region.py` vs the new main) and the w16 drift metrics.
  `data/repay_prices_5998913.json` (round 2): the best source knob at each byte delta.

**Cheapest knob per byte delta on 599891304** (dM vs 2,251; placeholder-removing genes such as dv*/devol/vb are listed
separately because cto-devoltie owns them):

| dB | -88 | -80 | -72 | -64 | -48 | -40 | -32 | -24 | -16 | -8 | 0 | +8 | +16 | +24..+56 | +72 | +88 | +120 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best dM | -15 | -14 | -15 | -13 | -36 | -14 | -3 | **-1** (t1n) | -10 | -3 (-1 with a placeholder gene) | 0 | -2 | 0 (g1+t1n) | -1..-2 | **+1** (crl2/crl3) | **+1** (crl3+g1+t1n) | **+2** (g1) |

So every lead above main needs a repay of 16-120 B, and the library's cheapest repay at those sizes costs at least 3 M,
except t1n (-24 B, -1 M), which g1/crl3 already contain.

## 2. Splice screens on 599891304 (`tools/scr16.py`, `tools/z3.py`; `data/screens_r1.json`, `data/pairs_valid_r2.json`)

| screen | priced | best at 27,400 B |
| --- | ---: | --- |
| every conflict-free zero-sum pair of the usable captures (M >= 2,200; round 1 pairs re-checked against the round-2 bases + every pair with a round-2 capture) | 5,000 | **2,251** (109 ties, all 0 B + 0 B); best traded pair 2,250 (cu_unwrapcur or wl_writ_eq + sh_iflet-containing `L2_rr0K`) |
| triples of the 39 0 B captures with M >= 2,250 | 3,650 | 2,251 (244 ties); every tie keeps main's 3,140 oracle slots except hkl3 (3,144) |
| g1 (27,520, 2,253) + 1-3 knobs | 0 | no conflict-free set: every -120 B set overlaps g1's validate hunks |
| crl3 (27,472, 2,252) + 1-3 knobs (each >= -4) | 3 | 2,237 (`a8c2_g_s7_dborrow`, -72 B) |
| crl3+t1n (27,448, 2,251) + 1-3 knobs (each >= -4) | 0 | every -48 B set in the library carries t1n |
| crl3+g1+t1n (27,488, 2,252) + 1-2 knobs | 2 | 2,239 (`c2_g_s7_dborrow`, -88 B) |
| g1+t1n (27,416, 2,251) + 1-2 knobs | 44 | 2,247 (`N_m_dv334` + `c2_L_share_none_first`; dv334 is a placeholder gene) |
| sh_iflet (27,392, 2,245) + 1-2 knobs to +8 B | 803 | 2,250 (`wl_writ_eq`, `cu_unwrapcur`; both built: 2,250) |
| w16a13 tAn2 (27,040, 2,219; source-outlined 307/312) + 1-3 knobs to +360 B | 0 | no set of <= 3 library knobs adds +360 B; positive knobs are worth <= +2 M each, so tAn2 would need ~17 of them |

**Perfect-repay bounds (deletion oracles, `tools/del2.py`, `tools/slotbound.py`).** Deleting any two 8 B instructions of
g1+t1n (jumps re-fixed) gives at most 2,252, and that +1 needs the deletion of the `max_fee` reload at cand 0x15b0
(`ldxdw r3,[r10-0x948]` before the 338 `jlt`), a register-allocation artefact. crl3+t1n is the best positional fit
measured (drift through the TCF is 0, so its positional slots fall to 3,063-3,082 with a late 48 B repay), but deleting 48 B
of its own unmatched code costs 3-5 M (2,246-2,248): the repay cannot be had for free even in the oracle. The same bound
for crl3+g1+t1n (27,488 B, 2,252), 11 unmatched instructions deleted inside one region: sweep head 2,248, TCF 2,242,
sharing CPI 2,248, post-CPI/native arm 2,249 (3,123 slots), wallet 2,248. So no -88 B repay keeps it above main either.

## 3. Recaptures and composite builds on 599891304 (raw-IR oracle, `tools/scr.py` + `tools/g16.py`; `data/res-5998913.jsonl`)

| name | genes | bytes | dB | M | dM |
| --- | --- | ---: | ---: | ---: | ---: |
| m0 | - | 27,400 | +0 | 2,251 | +0 |
| g1 | j13:g1 (`let creator=st.creator;` before validate) | 27,520 | +120 | 2,253 | +2 |
| crl3 / crl2 | crl3 / m_crl2 | 27,472 | +72 | 2,252 | +1 |
| t1n | t1n | 27,376 | -24 | 2,250 | -1 |
| shif | sh_iflet | 27,392 | -8 | 2,245 | -6 |
| a1 | a1 | 27,376 | -24 | 2,244 | -7 |
| I6n | I6n | 27,416 | +16 | 2,250 | -1 |
| hkl2 | hkl2 | 27,288 | -112 | 2,048 | -203 |
| hkcopy / hkl3 / q5 / lfb5 | hk_copy / hkl3 / j13:q5 / lit:b5:10234567 | 27,400 | 0 | 2,251 | 0 (neutral, not identical) |
| cuunw / colnat / wlwe | cu_unwrapcur / p_colnat / wl_writ_eq | 27,408 | +8 | 2,246 / 2,248 / 2,245 | -5 / -3 / -6 |
| gwclk | K_g_w_clock_local | 27,416 | +16 | 2,248 | -3 |
| cumatch / c2 / mv51 | cu_match / j13:c2 / mv_5_1 | 27,392 | -8 | 2,244 / 2,246 / 2,223 | -7 / -5 / -28 |
| evnf / shprog | ev_nf_inline / K_sh_prog_let | 27,376 / 27,368 | -24 / -32 | 2,239 / 2,239 | -12 / -12 |
| tsplit | tsplit | 27,456 | +56 | 2,139 | -112 |
| crl3t1n | crl3 + t1n | 27,448 | +48 | 2,251 | 0 |
| S1 / S2 | sh_iflet + cu_unwrapcur / wl_writ_eq | 27,400 | 0 | 2,250 / 2,250 | -1 / -1 (S2: 3,121 oracle slots) |
| ntA / ntB | hkl3 + lfb5 / lfb5 + lkb6 | 27,400 | 0 | 2,251 / 2,250 | 0 / -1 |

`amp_inline` no longer applies (A6 removed `amm_present` from that scope).

**g1 family (no splice price: g1's validate hunks overlap t1n's).** g1 + t1n is not additive in size (+16 B, not +96 B):

| name | genes | bytes | dB | M | dM |
| --- | --- | ---: | ---: | ---: | ---: |
| g1t1n | g1 + t1n | 27,416 | +16 | 2,251 | 0 |
| G1d | g1 + t3n (`if let None=new`) | 27,416 | +16 | 2,251 | 0 |
| G1i | g1 + t1n + l2l_cashback (0 B on this source) | 27,416 | +16 | 2,251 | 0 |
| G1c | tf_f6 (`let creator=a.bonding_curve.creator`) + t1n | 27,416 | +16 | 2,249 | -2 |
| G1b | cs7 (g1 with the target store first) + t1n | 27,424 | +24 | 2,249 | -2 |
| G1e / G1f / G1h | g1 + t1n + sh_iflet / c2 / cu_match | 27,408 | +8 | 2,246 / 2,247 / 2,245 | -5 / -4 / -6 |
| G1k | g1 + t1n + a1 | 27,392 | -8 | 2,245 | -6 |
| L1 | g1 + t1n + l2l_cashback + c2_L_share_none_first | 27,408 | +8 | 2,247 | -4 |
| C3a | crl3 + t1n + I6n | 27,440 | +40 | 2,249 | -2 |
| **C3b** | **crl3 + g1 + t1n** | 27,488 | +88 | **2,252** | +1 |
| cT1/cT3/cT4/cT5/cT1t | one entry creator copy `let cr=a.bonding_curve.creator` shared by the shared test, the arm's `target=cr` (and the CtoState literal) | 27,416-27,440 | +16..+40 | 1,913-1,918 | -333..-338 |
| cT6 | the same through `let cr=&a.bonding_curve.creator` | 27,560 | +160 | 1,587 | -664 |

Every -8 B knob added to g1+t1n costs 4-6 M. The shared entry copy (`cT*`) collapses: `cr` stays live across validate.

**CtoState block spellings (orig 0x420-0x540 copies the creator ascending from `r9=&curve.creator` after three bool
stores; main copies it descending from `r7+8` before them).**

| name | spelling | bytes | M | note |
| --- | --- | ---: | ---: | --- |
| csA | `let cref=&a.bonding_curve.creator;` before quote_locked, `creator:*cref` | 27,400 | 2,251 | byte-identical to main |
| csC | `creator:Pubkey::new_from_array(a.bonding_curve.creator.to_bytes())` | 27,400 | 2,251 | byte-identical |
| csI | `creator:{let c:&Pubkey=&a.bonding_curve.creator;*c}` | 27,400 | 2,251 | byte-identical |
| csF | `let creator=a.bonding_curve.creator;` before the literal, field shorthand | 27,400 | 2,250 | -1 |
| csH | `cref` shared by the shared test and the literal | 27,464 | 1,593 | collapses |
| **fl1** = fl3 | curve flags read before quote_locked (`let mayhem=..;let holder_reward=..;let cashback_coin=..;`, the original loads them right after the shared test and spills them) | **27,352** | 2,115 | **front +12** (entry.st +10, holder_head +2, fee_chain +1, join +1), back -148 (sweep head -15, TCF -60, sharing CPI -57, wallet -8) |
| fl2 | the same reads before the holder PDA | 27,464 | 1,579 | collapses |

fl1 is another faithful front (the original's early flag loads) whose back collapses under main's back-half tuning, the
pattern of VC (w16a05) and w16a09's unions. fl1's front spliced onto main's back (w16a05 `splice2.py`, clean: 157 calls,
error lines intact) is M 2,257 at 27,440 B (cut orig 0x750), 2,258 at 0x1008 and 2,260 at 27,464 B (cut 0x1c68): the
front is worth +9 and is 64 B longer than main's front, about the length the original's entry has over main's.
fl1 + crl3 + t1n collapses (27,512 B, 1,648) and fl1 + hkl3 stays in the fl1 basin (27,312 B, 2,111).

## 4. Near-tie table (M 2,250-2,251 with more original skeleton than main)

rfj = true LCS with frame, registers and jump offsets masked (w16 `decomp.py --drift`; main 3,001); jbad = jump
displacement mismatches among aligned jumps (main 112/262); drift = median (ours - orig) token offset by region.

| composite | bytes | M | rfj | jbad | drift entry / val tail / share CPI / event | status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| main | 27,400 | 2,251 | 3,001 | 112 | -22 / -21 / -13 / -6 | |
| **ntA = hkl3 + lfb5** | 27,400 | **2,251** | **3,004** | 112 | = main | built; tie with +3 skeleton, 3,144 oracle slots |
| lfb5 | 27,400 | 2,251 | 3,003 | 112 | = main | built |
| hkl3 | 27,400 | 2,251 | 3,002 | 112 | = main | built |
| ntB = lfb5 + lkb6 | 27,400 | 2,250 | 3,005 | 112 | = main | built |
| crl3 + t1n | 27,448 | 2,251 | 3,005 | 109 | **-13** / -12 / -7 / 0 | built; the entry drift moves 9 tokens toward the original |
| g1 + t1n | 27,416 | 2,251 | 3,004 | 114 | -22 / -22 / -11 / -4 | built; sharing CPI +6, tail +2, wallet -3, join -2 |
| crl3 + g1 + t1n | 27,488 | 2,252 | | | | built |
| sh_iflet + cu_unwrapcur (S1) | 27,400 | 2,250 | 2,999 | 114 | -22 / -21 / -13 / -5 | built |
| sh_iflet + wl_writ_eq (S2) | 27,400 | 2,250 | 3,000 | 113 | -22 / -21 / -12 / -6 | built; 3,121 oracle slots |
| sh_iflet + a1 (A6 + sh_iflet + a1) | 27,368 | 2,244 | 3,002 | 118 | | splice |

| hkl3 + lfb5 + lkb6 | 27,400 | 2,250 | 3,006 | 112 | = main | built |
| ST1 = sh_iflet + a1 + tsplit (w16a02) | 27,400 | 2,247 | 3,005 | 118 | -22 / -21 / -15 / -8 | built; 3,230 oracle slots |
| T1 = a1 + tsplit | 27,408 | 2,245 | 3,005 | 118 | -22 / -21 / -15 / -7 | built |
| L_vol = mv_5_1 + t1n + m_crl2 + vol334_back (w15a16) | 27,400 | 2,236 | 3,007 | 111 | -13 / -14 / -13 / -6 | built; 3,091 oracle slots; moves (does not remove) the 334 placeholder |
| mv_5_1 + t1n + m_crl2 (L_vol without the placeholder move) | 27,408 | 2,237 | | | | built |

H_hkl2crl3 (w15a03; skM +20 at M = main in w16a05) is not reproducible on the current source: it was built on 90300f9,
and hkl2 collapses once #3666 is in. The w15a01 `F_N6` (+8 B, 2,251 from ed47ac7) is I6n on the current source (+16 B,
2,250).

## 5. Two-region splice envelope over 4,288 archived builds (`idxM16b.npz`, w16a05 `pairs.py` + `splcheck.py`)

w16a05's index (3,576 builds) plus 712 unique builds made since (two harvests). The top 400 pairs are exact-priced each
round: 185 clean in round 1 and 237 of 398 in round 2 (157 calls and the original's error-line multiset;
`data/envelope16.json`). Best clean splice per front family:

| splice M | bytes | cut (orig) | front | back |
| ---: | ---: | --- | --- | --- |
| 2,290 | 27,584 | 0x648 entry.st | w16a09 `E2U` (GPF+Fa+V2+qli+hkt+p289n+vmt, M 1,530) | any main-like 0 B tie (q5, lfb5, hkl3, hkcopy) |
| 2,284 | 27,392 | 0x1c68 sweep_head | w16a05 `Lsh_k3` (VC, M 2,140) | w15a02 `M_g1` |
| 2,283 | 27,384 | 0x2c90 tcf | w15a35 `pd_b5x11` (PDA-first, RA decisions) | w14a133 `fru1` |
| 2,281 | 27,400 | 0x1c68 | w15a03 `L_N3h` (VC) | `M_g1` |
| 2,275 | 27,480 | 0x55b8 cold_err | w15a21 `cs7` | w16a08 `hc` (IR basin) |

Same shape as w16a05 found: a front family whose back collapses, plus a near-main back. The new front is w16a09's class
union E2U: its first 0x648 bytes are +41 over main's at +184 B, which is about the 22 tokens main lacks in the entry.

## Next ideas

1. The only above-main leads are size leads in the entry/validate (g1 +2 at +120 B, crl2/crl3 +1 at +72 B, crl3+g1+t1n +1
   at +88 B): main is 22 tokens short of the original there and long after the sharing CPI, so a faithful lead needs a
   faithful repay after the sweep. The library has none: below -24 B every repay costs >= 3 M (table in section 1).
2. crl3+t1n is the best positional fit seen (TCF drift 0); a source change that removes ~48 B of main-only code after the
   TCF without loss (xled's ours-only runs at cand 0x4068-0x4158 and 0x41f8-0x4300 in the sharing CPI build, and the join
   at 0x1830-0x1920) would make it land with fewer slots.
3. Rebuild the catalog before splicing: `tools/cat16b.py <out> --prev <old catalog>` reuses the per-capture work; then
   `scr16.py pairs|pairsnew|lead`. Translations of old-source captures are exact unless flagged.

## Tools (`tools/`, experiment only; paths point at this lane's `$OUT`)

- `cat16b.py` catalog builder (v2: base detection from res files and ledger keys, translation, A6/ev6-overlap flag,
  snapshots, incremental `--prev`), `cat16.py`/`tmh.py` (round-1 versions), `mkcat16.py` the committed export, `scr16.py`
  pair / pairs-with-new / lead screens, `z3.py` 0 B triple screen, `nt16.py` near-tie pricing with drift metrics,
  `del2.py` two-deletion bound, `slotbound.py` positional-slot bound for a size repay, `mkscreens.py` summaries, `g16.py`
  the union gene library (w16a02 genes_fk, w15a16 genes_mp incl. w15a03 genes_s15, w15a13 `e/*.py` as `j13:<name>`, w16a07
  `e/*.py` as `a07:<name>`, w15a30 `lit:<key>:<order>` literal permutations, and this lane's cs7/tf_f6/crlT*/ts_* genes),
  `scr.py` the raw-IR capture screen with `stitch16` ledger keys, `rec.py` ledger rows.
- Unchanged dependencies from w16a02 (`splice.py`, `oracle.py`, `drift.py`, `region.py`, `bdis.py`, `capraw.py`, `rx.py`,
  `delmap.py`, `insmapn.py`, `genes_fk.py`) and w16a05 (`idx.py`, `pairs.py`, `splcheck.py`, `xled.py`, `regprof.py`) are
  on those lanes' branches.
- Index pointers (not committed; rebuild with w16a05 `idx.py`): `$C/lanes/w16a17-cto-stitch16/data/idxM16b.npz` (M partners,
  4,288 builds), `idxM_new_r1.npz` / `idxM_new_r2.npz` (the per-harvest additions); catalogs `data/cat16_r1.json`,
  `data/cat16_r2.json` and the snapshots in `tx/` under the same lane dir.
