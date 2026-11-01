//! Host driver for `token_schedule_admission.rs`, used by
//! `tests/test_token_schedule_admission_captured.py`. One request per line:
//! `update fault fault ...`, where a fault is `<slot>.<kind>`. Answers are
//! `error:<code>`, `error:<name>`, or `ok,<events>,<stored mint is the mint>,<token account size>`.
#[path = "token_schedule_admission.rs"]
mod token_schedule_admission;

use std::io::{self, BufRead, Write};
use token_schedule_admission::{admit, Load, Request, Stop, TokenProgramSlot};

fn load(slot: &mut Load, kind: &str) {
    // The owner is checked first; a later data fault does not hide it.
    match kind {
        "missing" => *slot = Load::Missing,
        "owner" => *slot = Load::WrongOwner,
        _ if *slot == Load::WrongOwner => {}
        "short" => *slot = Load::Short,
        "disc" => *slot = Load::BadDiscriminator,
        "trunc" if *slot == Load::Stored => *slot = Load::Truncated,
        "trunc" => {} // keeps the data fault before it
        other => panic!("unknown load fault {other}"),
    }
}

fn answer(line: &str) -> String {
    let mut words = line.split_whitespace();
    words.next();
    let mut r = Request::default();
    let mut program_wrong = false;
    for word in words {
        let (slot, kind) = word.split_once('.').unwrap();
        match (slot, kind) {
            ("authority", "unsigned") => r.authority_unsigned = true,
            ("authority", "readonly") => r.authority_read_only = true,
            ("authority", _) => r.authority_stranger = true,
            ("global", "key") => r.global_wrong_address = true,
            ("global", k) => load(&mut r.global, k),
            ("global_volume_accumulator", "key") => r.accumulator_wrong_address = true,
            ("global_volume_accumulator", "readonly") => r.accumulator_read_only = true,
            ("global_volume_accumulator", k) => load(&mut r.accumulator, k),
            ("mint", "key") => r.mint_wrong_address = true,
            ("mint", k) => load(&mut r.mint, k),
            ("global_incentive_token_account", k) => match k {
                "key" => r.incentive.wrong_address = true,
                "readonly" => r.incentive.read_only = true,
                "owner" => r.incentive.foreign_owner = true,
                "short" => r.incentive.short = true,
                "mintdata" => r.incentive.wrong_mint = true,
                "ownerdata" => r.incentive.wrong_authority = true,
                "frozen" => {} // never read
                "missing" | "funded" => r.incentive.absent = true,
                other => panic!("unknown token fault {other}"),
            },
            ("associated_token_program", _) => r.associated_program_wrong = true,
            ("system_program", _) => r.system_program_wrong = true,
            ("token_program", "key") => r.token_program = TokenProgramSlot::Invalid,
            ("token_program", _) => r.token_program = TokenProgramSlot::OtherInterface,
            ("event_authority", _) => r.event_authority_wrong = true,
            ("program", _) => program_wrong = true,
            other => panic!("unknown fault {other:?}"),
        }
    }
    match admit(&r) {
        Err(Stop::Code(c)) => format!("error:{c}"),
        Err(Stop::InvalidAccountData) => "error:invalid_account_data".to_string(),
        Err(Stop::PrivilegeEscalation) => "error:privilege_escalation".to_string(),
        Err(Stop::MissingAccount) => "error:missing_account".to_string(),
        Ok(()) if program_wrong => "error:missing_account".to_string(),
        Ok(()) => "ok,1,1,165".to_string(),
    }
}

fn main() {
    let stdout = io::stdout();
    let mut out = stdout.lock();
    for line in io::stdin().lock().lines() {
        writeln!(out, "{}", answer(line.unwrap().trim())).unwrap();
    }
}
