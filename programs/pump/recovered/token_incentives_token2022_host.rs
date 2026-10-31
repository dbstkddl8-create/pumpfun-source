//! Host driver for `token_incentives_token2022.rs`, used by
//! `tests/test_token_incentives_token2022_captured.py`. One request per line:
//! `now,epoch,needs_claim,unclaimed,claimed,current_sol_volume,last_update,
//!  has_claimed,token_program,mint_owner,global_mint_ok,mint_truncated,fee,
//!  hook_set,paused,mint_non_transferable,default_frozen,vault,vault_address_ok,
//!  user_ata,user_address_ok`
//! on the schedule the test fixes, where a program is `t22|spl|system`, `fee`
//! is `-` or `older_bps:older_max:newer_epoch:newer_bps:newer_max`, and an
//! account is `missing|truncated|uninitialized` or `[wrong:]` followed by
//! `balance:frozen:fee_extension:owner_matches:mint_matches:memo:cpi_guard:non_transferable:hook_extension`.
//! Answers: `error:<code>`, `panic`, an instruction error name, or
//! `ok,<amount>,<withheld>,<created size>,<created state>,<user fields...>`.
#[path = "token_incentives.rs"]
#[allow(dead_code)]
mod token_incentives;
#[path = "token_incentives_token2022.rs"]
#[allow(dead_code)]
mod token_incentives_token2022;

use std::io::{self, BufRead, Write};
use token_incentives::{Global, User, DAYS};
use token_incentives_token2022::{Ata, Claim, Holding, Mint, Program, Stop, TransferFee};

const START: i64 = 1_700_000_000;
const DAY: i64 = 86_400;

fn holding(text: &str) -> Holding {
    let f: Vec<u64> = text.split(':').map(|v| v.parse().unwrap()).collect();
    Holding {
        balance: f[0],
        frozen: f[1] != 0,
        fee_extension: f[2] != 0,
        owner_matches: f[3] != 0,
        mint_matches: f[4] != 0,
        memo_required: f[5] != 0,
        cpi_guard: f[6] != 0,
        non_transferable: f[7] != 0,
        hook_extension: f[8] != 0,
    }
}

fn ata(text: &str) -> Ata {
    match text {
        "missing" => Ata::Missing,
        "truncated" => Ata::Truncated,
        "uninitialized" => Ata::Uninitialized,
        _ => match text.strip_prefix("wrong:") {
            Some(rest) => Ata::WrongProgram(holding(rest)),
            None => Ata::Held(holding(text)),
        },
    }
}

fn program(text: &str) -> Program {
    match text {
        "t22" => Program::Token2022,
        "spl" => Program::SplToken,
        _ => Program::Other,
    }
}

fn fee(text: &str) -> Option<TransferFee> {
    if text == "-" {
        return None;
    }
    let f: Vec<u64> = text.split(':').map(|v| v.parse().unwrap()).collect();
    Some(TransferFee { older_bps: f[0] as u16, older_max: f[1], newer_epoch: f[2], newer_bps: f[3] as u16, newer_max: f[4] })
}

fn answer(line: &str) -> String {
    let f: Vec<&str> = line.split(',').collect();
    let n = |k: usize| f[k].parse::<u64>().unwrap();
    let mut g = Global {
        start_time: START,
        end_time: START + 20 * DAY,
        seconds_in_a_day: DAY,
        total_token_supply: [0; DAYS],
        sol_volumes: [0; DAYS],
    };
    g.total_token_supply[1] = 1_000_000_000_000;
    g.sol_volumes[1] = 30_000_000_000;
    let mut u = User {
        needs_claim: n(2) != 0,
        total_unclaimed_tokens: n(3),
        total_claimed_tokens: n(4),
        current_sol_volume: n(5),
        last_update_timestamp: f[6].parse().unwrap(),
        has_total_claimed_tokens: n(7) != 0,
    };
    let c = Claim {
        token_program: program(f[8]),
        mint: Mint {
            owner: program(f[9]),
            matches_global: n(10) != 0,
            truncated: n(11) != 0,
            fee: fee(f[12]),
            hook_set: n(13) != 0,
            paused: n(14) != 0,
            non_transferable: n(15) != 0,
            default_frozen: n(16) != 0,
        },
        epoch: n(1),
        vault: ata(f[17]),
        vault_address_ok: n(18) != 0,
        user_ata: ata(f[19]),
        user_address_ok: n(20) != 0,
    };
    match token_incentives_token2022::claim(&c, &g, &mut u, f[0].parse().unwrap()) {
        Err(Stop::Code(code)) => format!("error:{code}"),
        Err(Stop::Panic) => "panic".to_string(),
        Err(other) => format!("{other:?}"),
        Ok(r) => format!(
            "ok,{},{},{},{},{},{},{},{},{},{}",
            r.amount,
            r.withheld,
            r.created_size,
            r.created_state,
            u.needs_claim as u8,
            u.total_unclaimed_tokens,
            u.total_claimed_tokens,
            u.current_sol_volume,
            u.last_update_timestamp,
            u.has_total_claimed_tokens as u8,
        ),
    }
}

fn main() {
    let stdout = io::stdout();
    let mut out = stdout.lock();
    for line in io::stdin().lock().lines() {
        writeln!(out, "{}", answer(line.unwrap().trim())).unwrap();
    }
}
