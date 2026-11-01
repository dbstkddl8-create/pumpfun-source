#![no_std]
#![feature(core_intrinsics, link_llvm_intrinsics)]
extern "C" { #[link_name="llvm.expect.i1"] fn expect(b: bool, v: bool) -> bool; }
extern "C" { fn g(x: u64) -> u64; fn h(x: u64) -> u64; fn k(x: u64) -> u64; }
#[no_mangle] pub fn f1(x: u64) -> u64 { if core::intrinsics::unlikely(x == 5) { unsafe{g(x)} } else { unsafe{h(x+1)} } }
#[no_mangle] pub fn f2(x: u64) -> u64 { if unsafe{expect(x == 6, false)} { unsafe{g(x+2)} } else { unsafe{h(x+3)} } }
#[cold] fn cold(){}
#[no_mangle] pub fn f3(x: u64) -> u64 { if x == 7 { cold(); unsafe{g(x+4)} } else { unsafe{k(x+5)} } }
