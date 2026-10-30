#!/usr/bin/env python3
"""Pump Fees update_fee_shares with shareholders that alias instruction accounts.

A shareholder key can equal an account that update_fee_shares already passes:
sharing_config, the creator vault, the update authority and so on. The stored
list drives remaining-account checks in pump_fees and the payout in pump, so
the same key then fills two slots of the CPI. Steps per case:

  u1  pump_fees update_fee_shares(new shareholders)  <- the measured step
  d2  fund the creator vault + pump distribute_creator_fees with the NEW list
  u3  a second update_fee_shares

The pump_fees image is the one under test. pump and pump_amm are the original
deployed images on both sides; they are CPI dependencies only. All state is
synthetic: fixed key seeds, fixed clock, a fresh LiteSVM per case and image,
no wall time and no paths in the results.

Usage: producer.py --root <repo> --images '{"original":..,"candidate":..}' --out <dir>
--images also accepts a path to a file holding that JSON object.
"""
import argparse
import base64
import gzip
import hashlib
import json
import pathlib

from solders.account import Account
from solders.clock import Clock
from solders.compute_budget import set_compute_unit_limit
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

PROGRAM = Pubkey.from_string("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ")
PUMP = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
AMM = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
TOKEN = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ATA_PROG = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
WSOL = Pubkey.from_string("So11111111111111111111111111111111111111112")
SYSTEM = Pubkey.default()

AUTH = Keypair.from_seed(bytes([231]) * 32)
PAYER = Keypair.from_seed(bytes([232]) * 32)
MINT = Pubkey.from_bytes(bytes([73]) * 32)
SHARING, SHARING_BUMP = Pubkey.find_program_address([b"sharing-config", bytes(MINT)], PROGRAM)
CURVE = Pubkey.find_program_address([b"bonding-curve", bytes(MINT)], PUMP)[0]
PUMP_GLOBAL = Pubkey.find_program_address([b"global"], PUMP)[0]
PUMP_VAULT = Pubkey.find_program_address([b"creator-vault", bytes(SHARING)], PUMP)[0]
EVENT = Pubkey.find_program_address([b"__event_authority"], PROGRAM)[0]
PUMP_EVENT = Pubkey.find_program_address([b"__event_authority"], PUMP)[0]
AMM_EVENT = Pubkey.find_program_address([b"__event_authority"], AMM)[0]
AMM_VAULT_AUTH = Pubkey.find_program_address([b"creator_vault", bytes(SHARING)], AMM)[0]
AMM_VAULT_ATA = Pubkey.find_program_address([bytes(AMM_VAULT_AUTH), bytes(TOKEN), bytes(WSOL)], ATA_PROG)[0]

# Non-executable shareholders: fixed byte-pattern keys that never sign.
HOLDERS = {n: Pubkey.from_bytes(bytes([110 + i]) * 32) for i, n in enumerate("ABCDEFGHIJ")}
# Executable shareholders: program accounts present in every world.
EXEC = {"X": TOKEN, "Y": ATA_PROG, "Z": SYSTEM, "P": PUMP, "M": AMM, "R": PROGRAM, "T": TOKEN22}
START = 1_700_000_000
GLOBAL_LEN = 740
STEP_FUND = 10_000_000


def disc(kind, name):
    return hashlib.sha256(f"{kind}:{name}".encode()).digest()[:8]


IX_UPDATE = disc("global", "update_fee_shares")
IX_DISTRIBUTE = disc("global", "distribute_creator_fees")
EV_UPDATE = disc("event", "UpdateFeeSharesEvent")
EV_DISTRIBUTE = disc("event", "DistributeCreatorFeesEvent")


ALIAS_KEYS = {"SC": SHARING, "VA": PUMP_VAULT, "CV": CURVE, "GL": PUMP_GLOBAL, "MI": MINT, "AU": AUTH.pubkey(), "PY": PAYER.pubkey(),
              "EV": EVENT, "PE": PUMP_EVENT, "AA": AMM_VAULT_AUTH, "WS": WSOL}


def key_of(name):
    if name in HOLDERS:
        return HOLDERS[name]
    if name in EXEC:
        return EXEC[name]
    if name == "AUTH":
        return AUTH.pubkey()
    if name == "W":  # a fresh non-executable key that is not a shareholder
        return Pubkey.from_bytes(bytes([99]) * 32)
    if name in ALIAS_KEYS:
        return ALIAS_KEYS[name]
    raise KeyError(name)


def holders_bytes(holders):
    out = len(holders).to_bytes(4, "little")
    for name, bps in holders:
        out += bytes(key_of(name)) + bps.to_bytes(2, "little")
    return out


def sharing_bytes(holders, version=2):
    data = disc("account", "SharingConfig") + bytes([SHARING_BUMP, version, 1]) + bytes(MINT)
    data += bytes(AUTH.pubkey()) + bytes([0]) + holders_bytes(holders)
    return data + bytes(1024 - len(data))


def curve_bytes():
    """pump BondingCurve: non-zero reserves (no AMM CPI), not complete, creator = sharing config."""
    data = disc("account", "BondingCurve")
    for value in [1_000_000_000, 30_000_000_000, 800_000_000, 1_000_000, 1_000_000_000_000]:
        data += value.to_bytes(8, "little")
    data += bytes([0]) + bytes(SHARING) + bytes(2) + bytes(32)
    return data + bytes(200 - len(data))


def decode_holders(raw, o):
    n = int.from_bytes(raw[o:o + 4], "little")
    o += 4
    items = []
    for _ in range(n):
        items.append([name_of(Pubkey.from_bytes(raw[o:o + 32])), int.from_bytes(raw[o + 32:o + 34], "little")])
        o += 34
    return items, o


def name_of(key):
    for table in (HOLDERS, EXEC):
        for n, k in table.items():
            if k == key:
                return n
    if key == AUTH.pubkey():
        return "AUTH"
    if key == key_of("W"):
        return "W"
    for n, k in ALIAS_KEYS.items():
        if k == key:
            return n
    return str(key)


def decode_sharing(d):
    if len(d) < 80:
        return None
    holders, end = decode_holders(d, 76)
    return {"version": d[9], "status": d[10], "admin_revoked": d[75], "holders": holders,
            "tail_nonzero": sum(1 for b in d[end:] if b)}


def decode_event(line):
    if not line.startswith("Program data: "):
        return None
    raw = base64.b64decode(line[len("Program data: "):])
    if raw[:8] == EV_UPDATE:
        holders, o = decode_holders(raw, 8 + 8 + 32 * 3)
        return {"event": "UpdateFeeSharesEvent", "new_shareholders": holders, "version": raw[o]}
    if raw[:8] == EV_DISTRIBUTE:
        holders, o = decode_holders(raw, 8 + 8 + 32 * 4)
        return {"event": "DistributeCreatorFeesEvent", "shareholders": holders,
                "distributed": int.from_bytes(raw[o:o + 8], "little")}
    return {"event": "unknown", "head": raw[:8].hex()}


class World:
    def __init__(self, fees_image, pump_image, amm_image, case):
        vm = LiteSVM()
        vm.set_clock(Clock(1000, START, 0, 0, START))
        vm.add_program_from_file(PROGRAM, fees_image)
        vm.add_program_from_file(PUMP, pump_image)
        vm.add_program_from_file(AMM, amm_image)
        self.vm = vm
        for kp in (AUTH, PAYER):
            vm.set_account(kp.pubkey(), Account(100_000_000_000, b"", SYSTEM))
        g = bytearray(GLOBAL_LEN)
        g[0:8] = disc("account", "Global")
        g[8] = 1
        vm.set_account(PUMP_GLOBAL, Account(10**9, bytes(g), PUMP))
        mint = bytearray(82)
        mint[44] = 6
        mint[45] = 1
        vm.set_account(MINT, Account(10**9, bytes(mint), TOKEN))
        wsol = bytearray(82)
        wsol[44] = 9
        wsol[45] = 1
        vm.set_account(WSOL, Account(10**9, bytes(wsol), TOKEN))
        vm.set_account(CURVE, Account(10**9, curve_bytes(), PUMP))
        vm.set_account(SHARING, Account(10**9, sharing_bytes(case["old"], case.get("version", 2)), PROGRAM))
        self.rent0 = vm.minimum_balance_for_rent_exemption(0)
        vm.set_account(PUMP_VAULT, Account(self.rent0 + case.get("vault", 0), b"", SYSTEM))
        for name, lamports in case.get("funded", {}).items():
            vm.set_account(key_of(name), Account(lamports, b"", SYSTEM))

    def remaining(self, names):
        return [AccountMeta(key_of(n), False, n not in EXEC) for n in names]

    def update_ix(self, new, remaining):
        a = [(EVENT, False, False), (PROGRAM, False, False), (AUTH.pubkey(), True, False),
             (PUMP_GLOBAL, False, False), (MINT, False, False), (SHARING, False, True), (CURVE, False, False),
             (PUMP_VAULT, False, True), (SYSTEM, False, False), (PUMP, False, False), (PUMP_EVENT, False, False),
             (AMM, False, False), (AMM_EVENT, False, False), (WSOL, False, False), (TOKEN, False, False),
             (ATA_PROG, False, False), (AMM_VAULT_AUTH, False, True), (AMM_VAULT_ATA, False, True)]
        metas = [AccountMeta(k, s, w) for k, s, w in a] + self.remaining(remaining)
        return Instruction(PROGRAM, IX_UPDATE + holders_bytes(new), metas)

    def distribute_ix(self, remaining):
        a = [(MINT, False, False), (CURVE, False, False), (SHARING, False, False), (PUMP_VAULT, False, True),
             (SYSTEM, False, False), (PUMP_EVENT, False, False), (PUMP, False, False)]
        return Instruction(PUMP, IX_DISTRIBUTE, [AccountMeta(k, s, w) for k, s, w in a] + self.remaining(remaining))

    def watched(self, names):
        keys = {"sharing_config": SHARING, "pump_creator_vault": PUMP_VAULT, "payer": PAYER.pubkey()}
        for n in names:
            if n not in EXEC:
                keys["holder:" + n] = key_of(n)
        return keys

    def snap(self, keys):
        out = {}
        for label, key in keys.items():
            a = self.vm.get_account(key)
            if a is None or (a.lamports == 0 and not a.data):
                out[label] = None
                continue
            out[label] = {"lamports": a.lamports, "owner": str(a.owner), "len": len(a.data),
                          "sha256": hashlib.sha256(bytes(a.data)).hexdigest()}
        return out

    def send(self, instructions, watch_names):
        vm = self.vm
        vm.expire_blockhash()
        signers = [PAYER]
        if any(m.pubkey == AUTH.pubkey() and m.is_signer for ix in instructions for m in ix.accounts):
            signers.append(AUTH)
        tx = Transaction.new_signed_with_payer([set_compute_unit_limit(1_400_000)] + instructions,
                                               PAYER.pubkey(), signers, vm.latest_blockhash())
        keys = self.watched(watch_names)
        before = self.snap(keys)
        r = vm.send_transaction(tx)
        failed = isinstance(r, FailedTransactionMetadata)
        meta = r.meta() if failed else r
        after = self.snap(keys)
        logs = list(meta.logs())
        sc = vm.get_account(SHARING)
        deltas = {k: ((after[k] or {}).get("lamports", 0) - (before[k] or {}).get("lamports", 0)) for k in keys}
        return {
            "transaction_sha256": hashlib.sha256(bytes(tx)).hexdigest(),
            "error": str(r.err()) if failed else None,
            "logs": logs,
            "events": [decode_event(l) for l in logs if l.startswith("Program data:")],
            "lamport_deltas": deltas,
            "accounts_after": after,
            "sharing_after": decode_sharing(bytes(sc.data)) if sc else None,
            "compute_units": meta.compute_units_consumed(),
        }


def holder_names(holders):
    return [n for n, _ in holders]


def run_case(paths, image, case):
    w = World(image, paths["pump"], paths["pump_amm"], case)
    old_names = case.get("remaining", holder_names(case["old"]))
    new = case["new"]
    names = sorted(set(old_names + holder_names(new) + holder_names(case["old"])) - set(EXEC),
                   key=lambda n: n) + [n for n in EXEC if n in set(old_names + holder_names(new))]
    steps = []
    if case.get("d0", True):
        steps.append(["d0", w.send([w.distribute_ix(holder_names(case["old"]))], names)])
    steps.append(["u1", w.send([w.update_ix(new, old_names)], names)])
    if steps[-1][1]["error"] is None or case.get("always_follow"):
        fund = transfer(TransferParams(from_pubkey=PAYER.pubkey(), to_pubkey=PUMP_VAULT, lamports=STEP_FUND))
        steps.append(["d2", w.send([fund, w.distribute_ix(holder_names(new))], names)])
        steps.append(["u3", w.send([w.update_ix([("J", 10000)], holder_names(new))], names)])
    return [{"step": s, **r} for s, r in steps]

BEHAVIOR = ["transaction_sha256", "error", "logs", "events", "lamport_deltas", "accounts_after", "sharing_after"]
ALIASES = {"SC": "sharing_config", "VA": "pump_creator_vault", "CV": "bonding_curve", "GL": "pump Global", "MI": "mint", "AU": "update authority",
           "PY": "transaction fee payer", "EV": "pump_fees event authority", "PE": "pump event authority", "AA": "AMM creator vault authority", "WS": "WSOL mint"}


def cases():
    out = []

    def add(name, note, old, new=None, **kw):
        out.append({"name": name, "note": note, "old": old, "new": [("J", 10000)] if new is None else new, "vault": V, "d0": False, **kw})
    V = 10_000_000
    add("control-two-holders", "two plain holders", [("A", 5000), ("B", 5000)])
    add("control-new-list", "new list with one plain holder, then the follow-up steps", [("A", 5000), ("B", 5000)], new=[("C", 10000)])
    for k, label in ALIASES.items():
        add("old-holder-" + k.lower(), f"stored holder = {label}", [("A", 5000), (k, 5000)])
    add("old-holder-sc-sole", "only stored holder = sharing_config", [("SC", 10000)])
    add("old-holder-va-sole", "only stored holder = pump_creator_vault", [("VA", 10000)])
    add("old-holder-sc-and-va", "stored holders = sharing_config and pump_creator_vault", [("SC", 5000), ("VA", 5000)])
    add("old-holder-sc-empty-vault", "stored holder = sharing_config, vault at the rent floor", [("A", 5000), ("SC", 5000)], vault=0)
    add("old-holder-va-empty-vault", "stored holder = pump_creator_vault, vault at the rent floor", [("A", 5000), ("VA", 5000)], vault=0)
    for k, label in ALIASES.items():
        add("new-holder-" + k.lower(), f"new list = {label}", [("A", 5000), ("B", 5000)], new=[(k, 10000)])
    add("old-duplicate-key", "stored list repeats one key", [("A", 5000), ("A", 5000)])
    add("old-duplicate-key-three", "stored list repeats one key among three", [("A", 2500), ("B", 2500), ("A", 5000)])
    add("new-duplicate-key", "new list repeats one key", [("A", 5000), ("B", 5000)], new=[("C", 5000), ("C", 5000)])
    add("remaining-repeats-first", "remaining accounts repeat the first holder", [("A", 5000), ("B", 5000)], remaining=["A", "A"])
    add("remaining-sc-in-holder-slot", "remaining slot of B holds sharing_config", [("A", 5000), ("B", 5000)], remaining=["A", "SC"])
    add("remaining-va-in-holder-slot", "remaining slot of B holds pump_creator_vault", [("A", 5000), ("B", 5000)], remaining=["A", "VA"])
    return out


def run_all(paths, case_list):
    rows = []
    for case in case_list:
        o, c = run_case(paths, paths["original"], case), run_case(paths, paths["candidate"], case)
        diffs = [f"{so['step']}:{k}" for so, sc in zip(o, c) for k in BEHAVIOR if so[k] != sc[k]]
        if len(o) != len(c):
            diffs.append("step_count")
        rows.append({"case": case, "original": o, "candidate": c, "behavior_match": not diffs, "diff": diffs,
                     "cu_match": [s["compute_units"] for s in o] == [s["compute_units"] for s in c]})
    return rows


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def gz_bytes(text):
    return gzip.compress(text.encode(), compresslevel=9, mtime=0)


def outcome(step):
    if step["error"] is None:
        return "ok"
    code = next((l.split("Error Code: ")[1].split(".")[0] for l in step["logs"] if "Error Code: " in l), None)
    return code or step["error"].split("Tagged(")[-1].split("Fieldless(")[-1].rstrip(")")


def summary(rows):
    out = []
    for r in rows:
        out.append({"case": r["case"]["name"], "note": r["case"]["note"], "behavior_match": r["behavior_match"], "cu_match": r["cu_match"],
                    "steps": [{"step": s["step"], "outcome": outcome(s), "cu": s["compute_units"], "cu_candidate": cs["compute_units"],
                               "deltas": {k.replace("holder:", ""): v for k, v in s["lamport_deltas"].items() if v and k != "payer"},
                               "stored_after": (s["sharing_after"] or {}).get("holders"),
                               "pump_log": next((l[:140] for l in s["logs"] if "Program log:" in l and not l.startswith("Program log: Instruction") and "pump_fees" not in l[:12]), None)}
                              for s, cs in zip(r["original"], r["candidate"])]})
    return out


def build(paths, case_list):
    rows = run_all(paths, case_list)
    receipts = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows)
    report = {
        "scope": "pump_fees update_fee_shares (v1) with shareholder keys equal to accounts already in the instruction; pump/pump_amm original images as CPI dependencies on both sides.",
        "images_sha256": {"original": sha(paths["original"]), "candidate": sha(paths["candidate"]), "pump_dependency": sha(paths["pump"]), "pump_amm_dependency": sha(paths["pump_amm"])},
        "case_count": len(rows), "step_count": sum(len(r["original"]) for r in rows),
        "behavior_mismatch_cases": [r["case"]["name"] for r in rows if not r["behavior_match"]],
        "cu_mismatch_cases": [r["case"]["name"] for r in rows if not r["cu_match"]],
        "receipts_sha256": hashlib.sha256(receipts.encode()).hexdigest(), "summary": summary(rows)}
    return gz_bytes(receipts), gz_bytes(json.dumps(report, sort_keys=True, indent=1) + "\n"), report


def load_images(arg):
    arg = arg.strip()
    return json.loads(arg if arg.startswith("{") else pathlib.Path(arg).read_text())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--images", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    images = load_images(a.images)
    root = pathlib.Path(a.root)
    paths = {"original": images["original"], "candidate": images["candidate"],
             "pump": str(root / "evidence/original/pump/deployed.so"), "pump_amm": str(root / "evidence/original/pump_amm/deployed.so")}
    rec, rep, report = build(paths, cases())
    out = pathlib.Path(a.out) / "runtime"
    out.mkdir(parents=True, exist_ok=True)
    (out / "receipts.jsonl.gz").write_bytes(rec)
    (out / "report.json.gz").write_bytes(rep)
    print(json.dumps({k: report[k] for k in ["case_count", "step_count", "behavior_mismatch_cases", "cu_mismatch_cases"]}))


if __name__ == "__main__":
    main()
