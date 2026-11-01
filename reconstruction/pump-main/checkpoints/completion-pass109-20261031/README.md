# Completion checkpoint — 2026-10-31

The fresh identity build binds **307 source files and 10 relative directories** using v3 admission. It includes the current contract source and new unlinked reference models. The [source snapshot](source-inputs.json), [build receipt](build.json) and [input hashes](input-bindings.json) identify the exact reviewed inputs.

Pump retains **1,034/1,035 raw and normalized matched windows (99.90%)**, with no losses against a fresh build of main `60a42309a`. The remaining `admin_cto::execute` window has **68.005%** instruction-token similarity, up from 67.436%, at 27,400 bytes. Its positional differences increase from 3,141 to 3,170; these are separate metrics. No new exact window is claimed. The executed Pump image changed, so the prior runtime receipt is not reused.

A fresh **388-case signed synthetic comparison** of this candidate against the captured Pump program passes with zero mismatches. All 776 original/candidate transaction signature vectors are nonempty and verify. This uses genuine dependency CPIs with pool authority nonsigner at the transaction boundary. It is finite runtime evidence, not whole-program equivalence. Prior stopped campaigns remain excluded.

Across the maintained checkpoints, **3,337/3,338 windows (99.97%)** and **5,185,728/5,213,128 code bytes (99.47%)** match. Whole meaningful ELF equality remains **4/5**. The four other program identity checkpoint receipts remain retained evidence. Separate bounded tests do not replace their identity acceptance.

- [Summary](summary.json), [full score](score.json.gz) and [fresh baseline score](baseline-score.json.gz).
- [Fresh runtime receipt](admin-runtime.json.gz) and [independent validation](runtime-validation.json).
- [Semantic review and ELF section comparison](semantic-review.json).

The selected source contains marked reconstruction shims tied to the pinned compiler, standard-library Rc layout and locked Anchor reference shapes. These improve measured bytes and do not establish historical source attribution or general portable Rust equivalence. See [current source review](source-peer-review.json). The externally merged Fees source update #3971 is reviewed separately in [its qualification audit](external-fees-review.json). Its new cold-build claim is author-reported; this checkpoint makes no new acceptance of that source. Historical source-bound Fees verifiers reject the changed canonical source. Historical checkpoints are unchanged. Hosted CI is tracked separately in the PR audit.
