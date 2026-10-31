//! Captured behavior of Pump `claim_token_incentives` through its token
//! interface, on top of the day rollover and claim in `token_incentives.rs`:
//! the Anchor checks of the two token accounts and the mint, the creation of a
//! missing user account for a mint with Token-2022 extensions, the transfer fee
//! on the way to the user, and the order of the failures.
//!
//! Checked against `evidence/original/pump/deployed.so` and the captured SPL
//! Token, Token-2022 and Associated Token programs by
//! `tests/test_token_incentives_token2022_captured.py`. Not linked into the
//! SBF crate. This is not a byte-identity claim.
//!
//! Unconfirmed (미확인, outside the checked inputs): extensions other than the
//! ones named here, a hook program that is really invoked, and interest-bearing
//! or scaled-amount mints.

use crate::token_incentives::{self, Global, Stop as BaseStop, User};

pub const CONSTRAINT_ASSOCIATED: u32 = 2009;
pub const CONSTRAINT_TOKEN_MINT: u32 = 2014;
pub const CONSTRAINT_TOKEN_OWNER: u32 = 2015;
pub const CONSTRAINT_ASSOCIATED_TOKEN_PROGRAM: u32 = 2023;
pub const ACCOUNT_OWNED_BY_WRONG_PROGRAM: u32 = 3007;
pub const INVALID_PROGRAM_ID: u32 = 3008;
pub const ACCOUNT_NOT_INITIALIZED: u32 = 3012;
pub const ACCOUNT_NOT_ASSOCIATED: u32 = 3014;
pub const INVALID_INCENTIVE_MINT: u32 = 6039;
pub const TOKEN_INSUFFICIENT_FUNDS: u32 = 1;
pub const TOKEN_MINT_MISMATCH: u32 = 3;
pub const TOKEN_INVALID_STATE: u32 = 13;
pub const TOKEN_ACCOUNT_FROZEN: u32 = 17;
pub const TOKEN_NO_MEMO: u32 = 36;
pub const TOKEN_NON_TRANSFERABLE: u32 = 37;
pub const TOKEN_CPI_GUARD_TRANSFER: u32 = 42;
pub const TOKEN_MINT_PAUSED: u32 = 67;

const SPL_ATA_SIZE: u64 = 165;
/// A Token-2022 account: the SPL layout, the type byte, ImmutableOwner.
const ATA_SIZE: u64 = 170;
const FROZEN: u8 = 2;
const INITIALIZED: u8 = 1;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Program {
    Token2022,
    SplToken,
    Other,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TransferFee {
    pub older_bps: u16,
    pub older_max: u64,
    pub newer_epoch: u64,
    pub newer_bps: u16,
    pub newer_max: u64,
}

impl TransferFee {
    pub fn withheld(&self, epoch: u64, amount: u64) -> u64 {
        let (bps, max) = if epoch >= self.newer_epoch {
            (self.newer_bps, self.newer_max)
        } else {
            (self.older_bps, self.older_max)
        };
        let fee = (u128::from(amount) * u128::from(bps)).div_ceil(10_000);
        fee.min(u128::from(max)) as u64
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Mint {
    pub owner: Program,
    /// The accumulator stores this mint.
    pub matches_global: bool,
    pub truncated: bool,
    pub fee: Option<TransferFee>,
    pub hook_set: bool,
    pub paused: bool,
    pub non_transferable: bool,
    pub default_frozen: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Holding {
    pub balance: u64,
    pub frozen: bool,
    pub fee_extension: bool,
    pub owner_matches: bool,
    pub mint_matches: bool,
    pub memo_required: bool,
    pub cpi_guard: bool,
    pub non_transferable: bool,
    pub hook_extension: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Ata {
    Missing,
    /// Well-formed data under the other token program.
    WrongProgram(Holding),
    Truncated,
    Uninitialized,
    Held(Holding),
}

#[derive(Clone, Copy, Debug)]
pub struct Claim {
    pub token_program: Program,
    pub mint: Mint,
    pub epoch: u64,
    pub vault: Ata,
    pub vault_address_ok: bool,
    pub user_ata: Ata,
    pub user_address_ok: bool,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Stop {
    Code(u32),
    InvalidAccountData,
    UninitializedAccount,
    IncorrectProgramId,
    MissingAccount,
    Panic,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct Claimed {
    pub amount: u64,
    pub withheld: u64,
    /// Size and state of the user account created here, 0 when it existed.
    pub created_size: u64,
    pub created_state: u8,
}

fn parsed(ata: &Ata) -> Result<Holding, Stop> {
    match ata {
        Ata::Missing => Err(Stop::Code(ACCOUNT_NOT_INITIALIZED)),
        Ata::Truncated => Err(Stop::InvalidAccountData),
        Ata::Uninitialized => Err(Stop::UninitializedAccount),
        Ata::WrongProgram(held) | Ata::Held(held) => Ok(*held),
    }
}

fn created_size(mint: &Mint, token_program: Program) -> u64 {
    if token_program == Program::SplToken {
        return SPL_ATA_SIZE;
    }
    let mut size = ATA_SIZE;
    if mint.fee.is_some() {
        size += 12;
    }
    if mint.hook_set {
        size += 5;
    }
    if mint.paused {
        size += 4;
    }
    if mint.non_transferable {
        size += 4;
    }
    size
}

/// Account loads run in field order, ahead of every constraint.
fn load(c: &Claim) -> Result<Holding, Stop> {
    let vault = parsed(&c.vault)?;
    if c.mint.owner == Program::Other {
        return Err(Stop::Code(ACCOUNT_OWNED_BY_WRONG_PROGRAM));
    }
    if c.mint.truncated {
        return Err(Stop::InvalidAccountData);
    }
    if c.token_program == Program::Other {
        return Err(Stop::Code(INVALID_PROGRAM_ID));
    }
    Ok(vault)
}

/// `init_if_needed` on the user account runs first among the constraints.
fn user_account(c: &Claim, claimed: &mut Claimed) -> Result<Holding, Stop> {
    if c.user_ata == Ata::Missing {
        if !c.user_address_ok {
            return Err(Stop::MissingAccount);
        }
        if c.mint.owner != c.token_program {
            return Err(Stop::IncorrectProgramId);
        }
        claimed.created_size = created_size(&c.mint, c.token_program);
        claimed.created_state = if c.mint.default_frozen { FROZEN } else { INITIALIZED };
        return Ok(Holding {
            balance: 0,
            frozen: c.mint.default_frozen,
            fee_extension: c.mint.fee.is_some(),
            owner_matches: true,
            mint_matches: true,
            memo_required: false,
            cpi_guard: false,
            non_transferable: c.mint.non_transferable,
            hook_extension: c.mint.hook_set,
        });
    }
    let held = parsed(&c.user_ata)?;
    if !held.mint_matches {
        return Err(Stop::Code(CONSTRAINT_TOKEN_MINT));
    }
    if !held.owner_matches {
        return Err(Stop::Code(CONSTRAINT_TOKEN_OWNER));
    }
    if matches!(c.user_ata, Ata::WrongProgram(_)) {
        return Err(Stop::Code(CONSTRAINT_ASSOCIATED_TOKEN_PROGRAM));
    }
    if !c.user_address_ok {
        return Err(Stop::Code(ACCOUNT_NOT_ASSOCIATED));
    }
    Ok(held)
}

/// The vault's mint is left to the token program.
fn vault_account(c: &Claim, vault: &Holding) -> Result<(), Stop> {
    if matches!(c.vault, Ata::WrongProgram(_)) {
        return Err(Stop::Code(CONSTRAINT_ASSOCIATED_TOKEN_PROGRAM));
    }
    if !vault.owner_matches {
        return Err(Stop::Code(CONSTRAINT_TOKEN_OWNER));
    }
    if !c.vault_address_ok {
        return Err(Stop::Code(CONSTRAINT_ASSOCIATED));
    }
    Ok(())
}

fn transfer(c: &Claim, source: &Holding, destination: &Holding, amount: u64) -> Result<u64, Stop> {
    if source.frozen {
        return Err(Stop::Code(TOKEN_ACCOUNT_FROZEN));
    }
    if source.balance < amount {
        return Err(Stop::Code(TOKEN_INSUFFICIENT_FUNDS));
    }
    if source.non_transferable {
        return Err(Stop::Code(TOKEN_NON_TRANSFERABLE));
    }
    if c.mint.owner != c.token_program {
        return Err(Stop::IncorrectProgramId);
    }
    if !source.mint_matches {
        return Err(Stop::Code(TOKEN_MINT_MISMATCH));
    }
    if c.mint.paused {
        return Err(Stop::Code(TOKEN_MINT_PAUSED));
    }
    if source.cpi_guard {
        return Err(Stop::Code(TOKEN_CPI_GUARD_TRANSFER));
    }
    if destination.frozen {
        return Err(Stop::Code(TOKEN_ACCOUNT_FROZEN));
    }
    if destination.memo_required {
        return Err(Stop::Code(TOKEN_NO_MEMO));
    }
    let withheld = c.mint.fee.map_or(0, |fee| fee.withheld(c.epoch, amount));
    if withheld != 0 && !destination.fee_extension {
        return Err(Stop::Code(TOKEN_INVALID_STATE));
    }
    if c.mint.hook_set {
        // The CPI carries no hook accounts, so a hook mint never gets through.
        let marked = source.hook_extension && destination.hook_extension;
        return Err(if marked { Stop::MissingAccount } else { Stop::InvalidAccountData });
    }
    Ok(withheld)
}

/// SPL Token does not look at the mint's owner, so a Token-2022 mint without
/// extensions goes through. Anything longer than its layouts does not parse.
fn spl_transfer(c: &Claim, source: &Holding, destination: &Holding, amount: u64) -> Result<u64, Stop> {
    if source.fee_extension || destination.fee_extension || c.mint.fee.is_some() {
        return Err(Stop::InvalidAccountData);
    }
    if source.frozen || destination.frozen {
        return Err(Stop::Code(TOKEN_ACCOUNT_FROZEN));
    }
    if source.balance < amount {
        return Err(Stop::Code(TOKEN_INSUFFICIENT_FUNDS));
    }
    if !source.mint_matches {
        return Err(Stop::Code(TOKEN_MINT_MISMATCH));
    }
    Ok(0)
}

/// Load order: vault, mint owner 3007, mint data, token program 3008. Then the
/// user account (create, or 2014, 2015, 2023, 3014), the accumulator's mint
/// 6039 and the vault (2023, 2015, 2009). Only then the handler: the schedule
/// update may panic, nothing due returns without a transfer, the transfer runs
/// and the claim is recorded last, so a token failure wins over the panic on an
/// overflowing claimed total.
pub fn claim(c: &Claim, g: &Global, u: &mut User, now: i64) -> Result<Claimed, Stop> {
    let vault = load(c)?;
    let mut claimed = Claimed::default();
    let user_account = user_account(c, &mut claimed)?;
    if !c.mint.matches_global {
        return Err(Stop::Code(INVALID_INCENTIVE_MINT));
    }
    vault_account(c, &vault)?;
    let to_stop = |stop: BaseStop| match stop {
        BaseStop::Code(code) => Stop::Code(code),
        BaseStop::Panic => Stop::Panic,
    };
    let mut updated = u.clone();
    token_incentives::update(g, &mut updated, now).map_err(to_stop)?;
    let amount = updated.total_unclaimed_tokens;
    if amount != 0 {
        claimed.amount = amount;
        claimed.withheld = match c.token_program {
            Program::SplToken => spl_transfer(c, &vault, &user_account, amount)?,
            _ => transfer(c, &vault, &user_account, amount)?,
        };
    }
    token_incentives::claim(g, u, now, vault.balance).map_err(to_stop)?;
    Ok(claimed)
}
