//! Captured account admission of Pump `admin_update_token_incentives`: which
//! accounts it refuses, with which code, and which refusal wins when several
//! are wrong. That includes `global_incentive_token_account`, the instruction's
//! `init_if_needed` slot.
//!
//! `token_schedule.rs` starts after admission. This model stops where that one
//! starts: it answers `Ok` when the handler runs. Recovered from
//! `evidence/original/pump/deployed.so` and checked against it on LiteSVM by
//! `tests/test_token_schedule_admission_captured.py`. Not linked into the SBF
//! crate. This is not a byte-identity claim.
//!
//! Admission runs in three stages. All other fields load first, in field order.
//! The `init_if_needed` slot then either creates the account or loads and checks
//! it, ahead of every other constraint. The constraints then run in field order.
//! `program` is not checked: a wrong one only fails the event self-CPI.
//!
//! Unconfirmed (미확인, outside the checked inputs): Token-2022 mints, and
//! accounts or mints between 4 bytes and their full length.

pub const CONSTRAINT_MUT: u32 = 2000;
pub const CONSTRAINT_SEEDS: u32 = 2006;
pub const CONSTRAINT_TOKEN_MINT: u32 = 2014;
pub const CONSTRAINT_TOKEN_OWNER: u32 = 2015;
pub const CONSTRAINT_TOKEN_PROGRAM: u32 = 2023;
pub const DISCRIMINATOR_NOT_FOUND: u32 = 3001;
pub const DISCRIMINATOR_MISMATCH: u32 = 3002;
pub const DID_NOT_DESERIALIZE: u32 = 3003;
pub const OWNED_BY_WRONG_PROGRAM: u32 = 3007;
pub const INVALID_PROGRAM_ID: u32 = 3008;
pub const NOT_SIGNER: u32 = 3010;
pub const NOT_INITIALIZED: u32 = 3012;
pub const NOT_ASSOCIATED_TOKEN_ACCOUNT: u32 = 3014;
pub const NOT_AUTHORIZED: u32 = 6000;

#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
pub enum Load {
    #[default]
    Stored,
    Missing,
    WrongOwner,
    /// Four bytes.
    Short,
    BadDiscriminator,
    /// The discriminator and nothing else.
    Truncated,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
pub enum TokenProgramSlot {
    #[default]
    Expected,
    /// Token-2022, with the SPL mint and token account left as they were.
    OtherInterface,
    Invalid,
}

#[derive(Clone, Copy, Default, Debug)]
pub struct IncentiveAccount {
    /// System owned with no data, whatever its lamports: created.
    pub absent: bool,
    pub wrong_address: bool,
    pub read_only: bool,
    pub foreign_owner: bool,
    /// Four bytes.
    pub short: bool,
    pub wrong_mint: bool,
    pub wrong_authority: bool,
}

#[derive(Clone, Copy, Default, Debug)]
pub struct Request {
    pub authority_unsigned: bool,
    pub authority_read_only: bool,
    /// Signed, but not `global.authority`.
    pub authority_stranger: bool,
    pub global: Load,
    pub global_wrong_address: bool,
    pub accumulator: Load,
    pub accumulator_wrong_address: bool,
    pub accumulator_read_only: bool,
    pub mint: Load,
    pub mint_wrong_address: bool,
    pub incentive: IncentiveAccount,
    pub associated_program_wrong: bool,
    pub system_program_wrong: bool,
    pub token_program: TokenProgramSlot,
    pub event_authority_wrong: bool,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Stop {
    Code(u32),
    InvalidAccountData,
    /// The create CPI, with a read-only payer or new account.
    PrivilegeEscalation,
    /// The create CPI, with the address it derives not among the accounts.
    MissingAccount,
}

fn code(c: u32) -> Stop {
    Stop::Code(c)
}

fn load_typed(load: Load) -> Result<(), Stop> {
    match load {
        Load::Stored => Ok(()),
        Load::Missing => Err(code(NOT_INITIALIZED)),
        Load::WrongOwner => Err(code(OWNED_BY_WRONG_PROGRAM)),
        Load::Short => Err(code(DISCRIMINATOR_NOT_FOUND)),
        Load::BadDiscriminator => Err(code(DISCRIMINATOR_MISMATCH)),
        Load::Truncated => Err(code(DID_NOT_DESERIALIZE)),
    }
}

fn load_mint(load: Load) -> Result<(), Stop> {
    match load {
        Load::Stored => Ok(()),
        Load::Missing => Err(code(NOT_INITIALIZED)),
        Load::WrongOwner => Err(code(OWNED_BY_WRONG_PROGRAM)),
        _ => Err(Stop::InvalidAccountData),
    }
}

fn load_stage(r: &Request) -> Result<(), Stop> {
    if r.authority_unsigned {
        return Err(code(NOT_SIGNER));
    }
    load_typed(r.global)?;
    load_typed(r.accumulator)?;
    load_mint(r.mint)?;
    if r.associated_program_wrong || r.system_program_wrong || r.token_program == TokenProgramSlot::Invalid {
        return Err(code(INVALID_PROGRAM_ID));
    }
    Ok(())
}

/// `init_if_needed`: an absent account goes to the Associated Token program, a
/// present one is checked here, field by field.
fn incentive_stage(r: &Request) -> Result<(), Stop> {
    let i = &r.incentive;
    if i.absent {
        let derives_elsewhere = i.wrong_address
            || r.accumulator_wrong_address
            || r.mint_wrong_address
            || r.token_program == TokenProgramSlot::OtherInterface;
        if derives_elsewhere {
            return Err(Stop::MissingAccount);
        }
        if r.authority_read_only || i.read_only {
            return Err(Stop::PrivilegeEscalation);
        }
        return Ok(());
    }
    if i.foreign_owner {
        return Err(code(OWNED_BY_WRONG_PROGRAM));
    }
    if i.short {
        return Err(Stop::InvalidAccountData);
    }
    if i.wrong_mint || r.mint_wrong_address {
        return Err(code(CONSTRAINT_TOKEN_MINT));
    }
    if i.wrong_authority || r.accumulator_wrong_address {
        return Err(code(CONSTRAINT_TOKEN_OWNER));
    }
    if r.token_program == TokenProgramSlot::OtherInterface {
        return Err(code(CONSTRAINT_TOKEN_PROGRAM));
    }
    if i.wrong_address {
        return Err(code(NOT_ASSOCIATED_TOKEN_ACCOUNT));
    }
    Ok(())
}

fn constraint_stage(r: &Request) -> Result<(), Stop> {
    if r.authority_read_only || r.incentive.read_only {
        return Err(code(CONSTRAINT_MUT));
    }
    if r.global_wrong_address {
        return Err(code(CONSTRAINT_SEEDS));
    }
    if r.authority_stranger {
        return Err(code(NOT_AUTHORIZED));
    }
    if r.accumulator_read_only {
        return Err(code(CONSTRAINT_MUT));
    }
    if r.event_authority_wrong {
        return Err(code(CONSTRAINT_SEEDS));
    }
    Ok(())
}

pub fn admit(r: &Request) -> Result<(), Stop> {
    load_stage(r)?;
    incentive_stage(r)?;
    constraint_stage(r)
}
