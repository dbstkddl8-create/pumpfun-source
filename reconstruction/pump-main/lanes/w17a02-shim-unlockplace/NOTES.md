# w17a02-shim-unlockplace: branch-hint shims for admin_cto block placement and inlining (notes)

Target `0x22a10` `admin_cto::execute` (`programs/pump/src/creator/admin_cto.rs`), pinned at 27,400 B.
Base: main 599891304 (origin/main 1647da0f2 has the same `programs/pump/src`): 0.67436, 3,141 slots, M 2,251.
Ledger: approach `shimunlock`, keys `0x22a10-w17-5998913-shimunlock-<trial>-v1`.

## 1. Which branch-hint spellings work on the identity toolchain (rustc 1.79.0-dev, LLVM 18.1.7)

`tools/hintprobe.sh` compiles `tools/hintprobe.rs` with the identity rustc for `sbpf-solana-solana` (about 1 s, no build
slot) and prints the optimized IR's branches and weights.

| spelling | `!prof` after `-O3` | why |
| --- | --- | --- |
| `core::intrinsics::unlikely(c)` / `likely(c)` (`#![feature(core_intrinsics)]`) | **none** | The intrinsic is codegen'd into a 1-byte alloca (`store`/`load`/`trunc`) before the branch. LowerExpectIntrinsic runs in the early function pipeline, before SROA, so it never sees `br (llvm.expect ..)` and drops the hint. |
| `extern "C"{#[link_name="llvm.expect.i1"]fn expect(b:bool,v:bool)->bool;}` (`#![feature(link_llvm_intrinsics)]`) | **`branch_weights 1:2000`** (or 2000:1) | The call returns an immediate `i1` that the `br` uses directly. The weight survives to llc. |
| `#[cold] fn cold(){}` called in the branch | none in the final IR | BPI's cold-call weight (1:16) exists only until `cold()` is inlined, so it steers the inliner and early passes, not llc. |

So `core::intrinsics::{likely,unlikely}` cannot steer anything here; a shim that needs a persistent weight must use the
`llvm.expect.i1` extern (y1-cto-llvm found the same on 2026-10-30). The feature gate goes on line 1 of `lib.rs`
(`#![feature(link_llvm_intrinsics)]` prepended, no new line). The gate plus the unused extern declaration is
byte-identical to main (trial `fgx`, sha `a8a70a59`). A hint is still lost when MIR re-tests the same value later
(`unwrap`, `?`, `unwrap_or_default` on the hinted Option/Result: MIR jump threading duplicates the test, y1). Reading the
payload through a raw pointer avoids the re-test.

## 2. Outline triggers as shims (full `measure.sh` builds; main 0.67436 / 27,400 B)

| trial | shim | bytes | ratio | note |
| --- | --- | ---: | ---: | --- |
| fgx | feature gate + extern decl only | 27,400 | 0.67436 | byte-identical |
| c306 | `cold()` at the head of the 306 Some arm | 26,992 | 0.58971 | outline + collapse (w14a07 C1 on main) |
| c3 | `cold()` inside the 307 and 312 error branches | 27,040 | 0.58887 | collapse |
| x307 | `expect(t==default,false)` on 307 | 27,256 | 0.57486 | collapse |
| x312 | `expect(..,false)` on both 312 compares | 27,232 | 0.65445 | |
| x3 | x307 + x312 | 27,040 | 0.58224 | collapse |
| tfc306 | tf_g3 creator binding + `cold()` at 306 Some | 27,024 | 0.66385 | = tf_g3_O class (outline, no llc-time weight) |
| tfx306n | tf_g3 + `if expect(new.is_some(),false){new.unwrap_or_default()}` | 27,456 | 0.67335 | no outline: the unwrap re-test drops the hint |

Every outline on main's own form collapses (as w15a25/w16a13 found for every V-time trigger). On the tf_g3 base the
transient cold call reproduces the IR-forced O base, so the remaining lever is the llc-time layout weight.
