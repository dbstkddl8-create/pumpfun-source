# w17a06-shim-irbeam: shim alphabet calibration and an IR beam over shim-expressible edits

Target `0x22a10` `admin_cto::execute` (`programs/pump/src/creator/admin_cto.rs`), pinned at 27,400 B.
Base: main 1647da0f2 / 11789175c (programs/ identical to 599891304): 0.67436, 3,141 slots, M 2,251 at 27,400 B.
Wave 17 SHIM track. Ledger: approach `irbeam`, keys `0x22a10-w17-1647da0-irbeam-<item>-v1`.

## 1. An exact pre-opt oracle in about 2 s (`tools/preslim.py` + `tools/fx.py`)

The raw-IR oracle (capraw pre-opt IR, `opt -O3`, slim, `llc`) runs `opt` on the whole 35 MB crate module. Under
this wave's machine load (load average 120-160) that takes 110 s wall per evaluation. `preslim.py` cuts the pre-opt
module down to what `execute` can see, and `fx.py` scores it. The result is **token-identical** to the full-module
oracle on main: 3,337 tokens equal, M 2,251 at 27,400 B, about 2 s wall.

How the reduction stays exact:
- keep every function and global in the reference closure of `execute` and `validate` (353 of 5,772 defines, about
  5% of the module). Every other define becomes a declaration, and unreachable metadata is pruned;
- add one `optnone noinline` caller, `@__keep_uses`, that calls each closure function which has callers outside the
  closure **and survives the full-module `opt -O3`** (`data/surv-1647da0.txt`: the full run's surviving defines, plus
  `slice_contains`). Without it a helper used by many handlers becomes single-use in the slim module. It then gets
  the LastCallToStatic inline bonus, or IPSCCP specialises it. For example, `slice_contains` with its one caller
  passing length 1 unrolls and reorders the `quote_locked` phi, which costs 8 B;
- the dummy call passes a constant wherever **every** call site in the full module passes that same constant,
  and an opaque `load volatile` from `@__opaque` everywhere else. Otherwise the dummy blocks IPSCCP/DAE argument
  removal that the full module does (`collect_transfer_native`'s constant last argument, +8 B).

Usage: `SURV=data/surv-1647da0.txt python3 tools/preslim.py raw.ll slim.ll keep` once per capture, then
`python3 tools/fx.py slim.ll <name>`. The `--mp` option adds Mperm and Mhc. Edits to admin_cto's own pre-opt bodies
(validate, execute, wallet, sweep) can be applied to `slim.ll` directly: `tools/gen.py` and `tools/screen.py` do that.
Re-derive the survivor list with one full `rx.py --keep` run when main's callees change.

Checks on source captures (full oracle or real build against slim):
| variant | full / build | slim |
| --- | --- | --- |
| main m0 | 2,251 @27,400 (full) | 2,251 @27,400, tokens identical |
| rv_par (`read_volatile(holder_key)` 32 B in validate 312) | 1,741 @28,168 (full) | 1,741 @28,168 |
| rv_own (w17a03 v4320 owner pin) | 0.67466 = 2,252 @27,400 (measure.sh, w17a03) | 2,252 @27,400 |

Caveat: like the full oracle, the slim oracle differs from the linked baseline build in 10 tokens. These are
use-list-order effects of the textual IR round trip. M is unchanged. Confirm final candidates with `measure.sh`.
