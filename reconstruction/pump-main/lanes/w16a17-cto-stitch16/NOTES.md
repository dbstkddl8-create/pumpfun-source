# w16a17-cto-stitch16: wave-16 integrator for admin_cto::execute (0x22a10)

Target `0x22a10` `admin_cto::execute` (`programs/pump/src/creator/admin_cto.rs`), pinned at 27,400 B.
Base: main 599891304 (admin_cto.rs as on 1f4e396b5: A6 + ev6): 0.67436, M 2,251, 3,141 slots (`$BASE`, not rebuilt; the
raw-IR capture `m0` reproduces it, `eq_main: true`). Successor of w16a02-cto-faithknobs (#3858) and w16a05-cto-skelsplice
(#3869). Ledger approach `stitch16`, keys `0x22a10-w16-5998913-stitch16-<name>-v1`.

**Result so far: notes only. No composite of the cached library reaches M 2,252 at 27,400 B.** The library is now one
catalog on the current main (old-source captures translated onto A6+ev6), the splice oracle reproduces every new-main
recapture and every built composite tested here byte for byte (one size miss, L1), and every size lead that is above main
alone (g1 +2, crl3/crl2 +1) has no repay set in the library that keeps it above main at 27,400 B.

M is the masked difflib match count of measure.sh: ratio = 2M / (6676 + (bytes - 27400)/8), so +1 M = +0.0003.

## 1. One catalog on the current main (`tools/cat16.py`, `tools/tmh.py`, `data/sizeknobs-w16b.json`)

- Every `rx/*/fn.bin` of the w15/w16 lanes: 4,611 paths, 1,990 unique builds (1,982 within 26-29 KB).
- Base of each capture: the lane's `res-<sha7>.jsonl` file or the ledger key's main sha7; otherwise the nearer of the two
  mains by instruction-diff size. Known old source (9bd38c7/86e2a6b/9120883/1cc4879) 891, known new (1f4e396/5998913) 195,
  older sources (90300f9 and before, e.g. w15a03's `H_*` rows) 326 (left out), guessed 570.
  The size-only guess misfiles old captures that contain one of main's two hunks: `ev_6012345789abc` alone looks "new"
  (it lacks only A6), and translating it applies ev6 twice. Both fixes are in the catalog.
- Old-source captures are translated onto the new main with the splice oracle: `splice(old main, [new main, capture])`,
  i.e. the capture's own local change applied on top of A6+ev6. A capture whose own diff overlaps the A6 or ev6 hunks
  (old-main token ranges 1115-1133 and 2425-2495) is flagged `touches_main_hunks` (226) and skipped by the screens.
- **Validation:** 16 single genes recaptured on 599891304 (section 3) are byte-identical (masked) to their translations,
  g1 included. The composites crl3+t1n, sh_iflet+cu_unwrapcur, sh_iflet+wl_writ_eq and hkl3+lfb5 are byte-identical to the
  splice of their singles. g1+t1n conflicts in the splice (their validate hunks overlap; the build is not additive in size:
  +16 B, not +96 B).
- `data/sizeknobs-w16b.json`: one row per usable source capture with M >= 2,150 on the new main: bytes/M on the new main,
  base and base sha, provenance (genes or ledger hypothesis), where the bytes land (`region.py` vs the new main) and the w16
  drift metrics for near-main rows. Same shape idea as w16a02's `sizeknobs-w16.json`, re-based.

## 2. Splice screens on 599891304 (`tools/scr16.py`, `tools/z3.py`)

| screen | composites priced | best at 27,400 B |
| --- | ---: | --- |
| every conflict-free zero-sum pair of 557 source captures (M >= 2,200 on the new main) | 7,161 | **2,251** (111 ties, all 0 B + 0 B); best pair with a byte trade 2,250 (`cu_unwrapcur` + w15a03 `rr0K`) |
| g1 (27,520, 2,253) + 1-3 knobs, pairs to dM -24, triples of knobs >= -12 | 0 | no conflict-free set: every -120 B set overlaps g1's validate hunks |
| crl3 (27,472, 2,252) + 1-3 knobs (knobs >= -4) | 3 | 2,237 (`a8c2_g_s7_dborrow`, -72 B) |
| crl3+t1n (27,448, 2,251) + 1-3 knobs (knobs >= -4) | 0 | all 3,454 candidate -48 B sets carry t1n |
| g1+t1n (27,416, 2,251) + 1-2 knobs | 49 | 2,247 (`l2l_cashback` + `c2_L_share_none_first`; built: 27,408 B, 2,247) |
| sh_iflet (27,392, 2,245) + 1-2 knobs to +8 B | 803 | 2,250 (`wl_writ_eq`, `cu_unwrapcur`; both built: 2,250) |
| w16a13 tAn2 (27,040, 2,219; source-outlined 307/312) + 1-3 knobs to +360 B | 0 | no set of <= 3 catalogued knobs adds +360 B |
| triples of the 39 0 B captures with M >= 2,250 | (see data) | (see data) |

The four size leads above main alone are all repaid below main: the library has no -24..-120 B knob cheaper than -1 M,
and the cheap ones (t1n, l2l_cashback, dv*) overlap the leads' validate/CtoState hunks.

Perfect-repay bound for g1+t1n (`tools/del2.py` over w16a02 `delmap.py`): deleting any two 8 B instructions of the
27,416 B build (jumps re-fixed) gives at most **2,252**, and the +1 needs the deletion of the `max_fee` reload at cand
0x15b0 (`ldxdw r3,[r10-0x948]` before the 338 `jlt`), a register-allocation artefact. So even an ideal -16 B source repay
of g1+t1n is worth +1 at most.

## 3. Recaptures on 599891304 (raw-IR oracle, `tools/scr.py` + `tools/g16.py`; `data/res-5998913.jsonl`)

| name | genes | bytes | dB | M | dM |
| --- | --- | ---: | ---: | ---: | ---: |
| m0 | - | 27,400 | +0 | 2,251 | +0 |
| g1 | j13:g1 (`let creator=st.creator;` before validate) | 27,520 | +120 | 2,253 | +2 |
| crl3 | crl3 | 27,472 | +72 | 2,252 | +1 |
| crl2 | m_crl2 | 27,472 | +72 | 2,252 | +1 |
| t1n | t1n | 27,376 | -24 | 2,250 | -1 |
| shif | sh_iflet | 27,392 | -8 | 2,245 | -6 |
| a1 | a1 | 27,376 | -24 | 2,244 | -7 |
| I6n | I6n | 27,416 | +16 | 2,250 | -1 |
| crl3t1n | crl3+t1n | 27,448 | +48 | 2,251 | +0 |
| g1t1n | j13:g1+t1n | 27,416 | +16 | 2,251 | +0 |
| hkl2 | hkl2 | 27,288 | -112 | 2,048 | -203 (collapses since #3666; w15a03 `H_hkl2` was built on 90300f9) |
| hkcopy / hkl3 / q5 / lfb5 | hk_copy / hkl3 / j13:q5 / lit:b5:10234567 | 27,400 | 0 | 2,251 | 0 (neutral, not identical) |
| cuunw / colnat / wlwe | cu_unwrapcur / p_colnat / wl_writ_eq | 27,408 | +8 | 2,246 / 2,248 / 2,245 | -5 / -3 / -6 |
| gwclk | K_g_w_clock_local | 27,416 | +16 | 2,248 | -3 |
| cumatch / c2 / mv51 | cu_match / j13:c2 / mv_5_1 | 27,392 | -8 | 2,244 / 2,246 / 2,223 | -7 / -5 / -28 |
| evnf / shprog | ev_nf_inline / K_sh_prog_let | 27,376 / 27,368 | -24 / -32 | 2,239 / 2,239 | -12 / -12 |
| tsplit | tsplit | 27,456 | +56 | 2,139 | -112 |
| S1 / S2 | sh_iflet + cu_unwrapcur / wl_writ_eq | 27,400 | 0 | 2,250 / 2,250 | -1 / -1 |
| L1 | g1 + t1n + l2l_cashback + c2_L_share_none_first | 27,408 | +8 | 2,247 | -4 |
| ntA | hkl3 + lfb5 | 27,400 | 0 | 2,251 | 0 |
| ntB | lfb5 + lkb6 | 27,400 | 0 | 2,250 | -1 |

`amp_inline` no longer applies (A6 removed `amm_present` from that scope).

## 4. Near-tie table (M 2,250-2,251 with more original skeleton than main)

rfj = true LCS with frame, registers and jump offsets masked (w16 `decomp.py --drift`; main 3,001); jbad = jump
displacement mismatches among aligned jumps (main 112/262); drift = median (ours - orig) token offset by region.

| composite | bytes | M | rfj | jbad | drift entry / val tail / share CPI / event | status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| main | 27,400 | 2,251 | 3,001 | 112 | -22 / -21 / -13 / -6 | |
| **ntA = hkl3 + lfb5** | 27,400 | **2,251** | **3,004** | 112 | = main | built; tie with +3 skeleton |
| lfb5 | 27,400 | 2,251 | 3,003 | 112 | = main | built |
| hkl3 | 27,400 | 2,251 | 3,002 | 112 | = main | built |
| ntB = lfb5 + lkb6 | 27,400 | 2,250 | 3,005 | 112 | = main | built |
| crl3 + t1n | 27,448 | 2,251 | 3,005 | 109 | **-13** / -12 / -7 / 0 | built; the entry drift moves 9 tokens toward the original |
| g1 + t1n | 27,416 | 2,251 | 3,004 | 114 | -22 / -22 / -11 / -4 | built; sharing CPI +6, tail +2, wallet -3, join -2 |
| sh_iflet + cu_unwrapcur | 27,400 | 2,250 | 2,999 | 114 | -22 / -21 / -13 / -5 | built (S1) |
| sh_iflet + wl_writ_eq | 27,400 | 2,250 | 3,000 | 113 | -22 / -21 / -12 / -6 | built (S2), 3,121 slots |
| sh_iflet + a1 (A6 + sh_iflet + a1) | 27,368 | 2,244 | 3,002 | 118 | | splice |

H_hkl2crl3 (w15a03, skM +20 at M = main in w16a05) and L_vol (w15a16) are not reproducible on the current source: H_ was
built on 90300f9, and hkl2 collapses (27,288 B, -203) once #3666 is in; L_vol's rx dir no longer exists.

## 5. Two-region splice envelope over 4,069 archived builds (`idxM16.npz`, w16a05 `pairs.py` + `splcheck.py`)

w16a05's index (3,576 builds) plus the 493 unique builds made since. 400 top pairs exact-priced, 185 clean (157 calls and
the original's error-line multiset). Best clean splice per front family:

| splice M | bytes | cut (orig) | front | back |
| ---: | ---: | --- | --- | --- |
| 2,289 | 27,584 | 0x698 entry.st | w16a09 `E2U` (GPF+Fa+V2+qli+hkt+p289n+vmt, M 1,530) | w16a15 `qKLD` |
| 2,284 | 27,392 | 0x1c68 sweep_head | w16a05 `Lsh_k3` (VC, M 2,140) | w15a02 `M_g1` |
| 2,283 | 27,384 | 0x2c90 tcf | w15a35 `pd_b5x11` (PDA-first, RA decisions) | w14a133 `fru1` |
| 2,281 | 27,400 | 0x1c68 | w15a03 `L_N3h` (VC) | `M_g1` |
| 2,275 | 27,480 | 0x55b8 cold_err | w15a21 `cs7` | w16a08 `hc` (IR basin) |

Same shape as w16a05 found: a front family whose back collapses, plus a near-main back. The new front is w16a09's class
unions (+38 at the entry.st cut).

## Tools (`tools/`, experiment only; paths point at this lane's `$OUT`)

- `cat16.py` catalog builder (base detection, translation, provenance), `tmh.py` main-hunk overlap flag, `mkcat16.py` the
  committed export, `scr16.py` pair / triple / lead screens, `z3.py` 0 B triple screen, `nt16.py` near-tie pricing with
  drift metrics, `g16.py` the union gene library (w16a02 genes_fk, w15a16 genes_mp incl. w15a03 genes_s15, w15a13
  `e/*.py` as `j13:<name>`, w16a07 `e/*.py` as `a07:<name>`, w15a30 `lit:<key>:<order>` literal permutations), `scr.py`
  the raw-IR capture screen with `stitch16` ledger keys, `rec.py` ledger rows.
- Unchanged dependencies from w16a02 (`splice.py`, `oracle.py`, `drift.py`, `region.py`, `bdis.py`, `capraw.py`, `rx.py`,
  `delmap.py`, `insmapn.py`, `genes_fk.py`) and w16a05 (`idx.py`, `pairs.py`, `splcheck.py`, `xled.py`, `regprof.py`) are
  on those lanes' branches.
- Index pointers (not committed, rebuild with w16a05 `idx.py`): `$C/lanes/w16a17-cto-stitch16/data/idxM16.npz` (M partners,
  4,069 builds), `idxM_new_r1.npz` (the 493 new builds); catalog `$C/lanes/w16a17-cto-stitch16/data/cat16_r1.json`.
