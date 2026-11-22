"""Controller-only generator and independent acceptance for the warehouse project."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

PROJECT_ENTRY = "billing_test.nex"
CONTEXT_SYMBOL = "warehouse::invoice::quote"

SOURCES = {
    "models.nex": """module warehouse::models;

// Rental and outage boundaries are whole days in the same calendar.
pub struct Period { start: i64; stop: i64; }
pub struct Rental { period: Period; climate: bool; member: bool; credit: i64; }
pub struct Invoice { days: i64; service: i64; discount: i64; tax: i64; due: i64; }
""",
    "calendar.nex": """module warehouse::calendar;
import "./models.nex" as models;

pub fn days(period: models::Period) -> i64 {
  if period.stop <= period.start { return 0; }
  return period.stop - period.start;
}

pub fn clip(period: models::Period, rental: models::Period) -> models::Period {
  var start: i64 = period.start;
  var stop: i64 = period.stop;
  if start < rental.start { start = rental.start; }
  if stop > rental.stop { stop = rental.stop; }
  return models::Period(start, stop);
}
""",
    "availability.nex": """module warehouse::availability;
import "./models.nex" as models;
import "./calendar.nex" as calendar;

// Source events arrive sorted by start day. Days outside the rental belong
// to other invoices and never reduce this period's availability.
pub fn unavailable(rental: models::Period, outages: list<models::Period>) -> i64 {
  var covered: i64 = 0;
  var frontier: i64 = rental.start;
  var index: i64 = 0;
  while index < len(outages) {
    let event: models::Period = calendar::clip(outages[index], rental);
    if event.start < event.stop {
      var first: i64 = event.start;
      if first < frontier { first = frontier; }
      if first < event.stop { covered = covered + event.stop - first; }
      frontier = event.stop;
    }
    index = index + 1;
  }
  return covered;
}
""",
    "meter.nex": """module warehouse::meter;
import "./models.nex" as models;
import "./calendar.nex" as calendar;
import "./availability.nex" as availability;

pub fn billable(rental: models::Period, outages: list<models::Period>) -> i64 {
  let rented: i64 = calendar::days(rental);
  let lost: i64 = availability::unavailable(rental, outages);
  if lost >= rented { return 0; }
  return rented - lost;
}
""",
    "tariff.nex": """module warehouse::tariff;

pub fn storage(days: i64) -> i64 {
  if days <= 5 { return days * 230; }
  return 5 * 230 + (days - 5) * 180;
}
pub fn climate(days: i64, enabled: bool) -> i64 {
  if enabled { return days * 35; }
  return 0;
}
pub fn handling(days: i64) -> i64 {
  if days == 0 { return 0; }
  return 125;
}
""",
    "benefits.nex": """module warehouse::benefits;

pub fn discount(storage: i64, member: bool) -> i64 {
  if member { return storage / 10; }
  return 0;
}
pub fn balance(gross: i64, credit: i64) -> i64 {
  if credit >= gross { return 0; }
  return gross - credit;
}
""",
    "tax.nex": """module warehouse::tax;

// Half-cent rounds up; all amounts are nonnegative cents.
pub fn sales_tax(amount: i64) -> i64 { return (amount + 10) / 20; }
""",
    "invoice.nex": """module warehouse::invoice;
import "./models.nex" as models;
import "./meter.nex" as meter;
import "./tariff.nex" as tariff;
import "./benefits.nex" as benefits;
import "./tax.nex" as tax;

pub fn quote(rental: models::Rental, outages: list<models::Period>) -> models::Invoice {
  let days: i64 = meter::billable(rental.period, outages);
  let storage: i64 = tariff::storage(days);
  let service: i64 = storage + tariff::climate(days, rental.climate) + tariff::handling(days);
  let rebate: i64 = benefits::discount(storage, rental.member);
  let sales: i64 = tax::sales_tax(service - rebate);
  let due: i64 = benefits::balance(service - rebate + sales, rental.credit);
  return models::Invoice(days, service, rebate, sales, due);
}
""",
}

# (rental_start, rental_stop, sorted outages, climate, member, credit)
VISIBLE = (0, 30, [(-3, 4), (6, 17), (9, 11), (13, 19), (26, 32)], True, True, 150)
CASES = (
    VISIBLE, (12, 12, [(1, 30)], True, True, 30),
    (-4, 2, [], False, False, 90), (20, 25, [(3, 4), (25, 27)], True, False, 30),
    (0, 20, [(0, 12), (0, 12), (4, 6), (7, 8), (10, 19)], False, False, 0),
    (0, 15, [(0, 3), (3, 7), (7, 7), (7, 14)], False, True, 700),
    (-2, 18, [(-20, -5), (-2, 9), (0, 3), (2, 4), (5, 12), (15, 20)], True, False, 0),
    (1, 16, [(1, 6), (2, 4), (5, 9), (11, 13)], False, True, 99),
    (1, 9, [(-7, 20), (0, 4), (5, 7)], True, False, 1),
    (9, 15, [(10, 11)], False, False, 0),
    (9, 15, [(10, 10)], False, False, 0),
    (9, 20, [(13, 19)], True, True, 5),
    (4, 19, [(4, 10), (6, 9), (11, 12)], True, False, 10000),
    (0, 28, [(3, 18), (6, 12), (8, 10), (11, 16), (15, 23), (27, 29)], False, True, 0),
)


def oracle(case):
    begin, end, outages, climate, member, credit = case
    # Enumerate independent calendar days, not production's interval sweep.
    billable = sum(not any(a <= day < b for a, b in outages) for day in range(begin, end))
    storage = 230 * min(5, billable) + 180 * max(billable - 5, 0)
    service = storage + 35 * billable * climate + 125 * bool(billable)
    discount = storage // 10 if member else 0
    tax = (service - discount + 10) // 20
    return billable, service, discount, tax, max(0, service - discount + tax - credit)


IMPORTS = '''import "./models.nex" as m;
import "./invoice.nex" as invoice;'''


def expressions(case):
    start, stop, events, climate, member, credit = case
    period = f"m::Period({start}, {stop})"
    outages = "[" + ", ".join(f"m::Period({a}, {b})" for a, b in events) + "]"
    rental = f"m::Rental({period}, {str(climate).lower()}, {str(member).lower()}, {credit})"
    return period, rental, outages


def visible():
    _, rental, outages = expressions(VISIBLE)
    return f"""module warehouse::billing_test;
{IMPORTS}

fn main() -> unit {{}}
test fn disputed_storage_invoice() -> unit {{
  let rental: m::Rental = {rental};
  let events: list<m::Period> = {outages};
  let statement: m::Invoice = invoice::quote(rental, events);
  assert(statement.due == {oracle(VISIBLE)[-1]});
}}
"""


def held_out():
    lines = ['module warehouse::acceptance;', IMPORTS, 'import "./meter.nex" as meter;',
             'import "./availability.nex" as availability;', 'fn main() -> unit {}']
    for index, case in enumerate(CASES):
        period, rental, outages = expressions(case)
        actual = oracle(case)
        invoice = "m::Invoice(" + ", ".join(map(str, actual)) + ")"
        lines += [f"test fn policy_{index}() -> unit {{", f"  let events: list<m::Period> = {outages};",
                  f"  assert(availability::unavailable({period}, events) == {case[1] - case[0] - actual[0]});",
                  f"  assert(meter::billable({period}, events) == {actual[0]});",
                  f"  assert(invoice::quote({rental}, events) == {invoice});", "}"]
    # Run a single native driver to avoid one cold link per data row.
    bodies = "\n".join(lines).replace("test fn policy_", "fn policy_")
    calls = " ".join(f"policy_{i}();" for i in range(len(CASES)))
    return bodies + "\ntest fn hidden_billing_contract() -> unit { " + calls + " }\n"


POLICY = """# Depot Ledger

Depot Ledger bills storage rentals in whole calendar days, using integer cents.
Its receipt is used both by Finance and by the operations dashboard. Public
module interfaces and existing callers must keep working.

A rental and each outage use half-open intervals [start, stop). Event starts
arrive in ascending order; events may overlap, share endpoints or nest. An
unavailable rental day is excluded once regardless of how many notices cover it.
An empty event or a notice outside the rental has no effect.

The storage tariff is 230 cents per billable day for the first five days and
180 cents for each additional day. Climate control adds 35 cents per billable
day. The handling charge is 125 cents for a nonempty bill and zero if no day
is billable. A member earns a ten percent discount on storage alone, rounded
down. Sales tax is five percent of the discounted subtotal including fees,
rounded to the nearest cent with ties up. Nonnegative account credit applies
last and cannot reduce the balance below zero.

Run ./nex test billing_test.nex --json for the disputed invoice. The public
calculation starts at warehouse::invoice::quote. Adjust application code only.
"""
PROTECTED = {"README.md": POLICY, PROJECT_ENTRY: visible(),
             "nex.json": '{"schema":"nex.project/1","language":"0.30","entry":"billing_test.nex"}\n'}


def create(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, value in {**SOURCES, **PROTECTED}.items():
        with (root / name).open("x", encoding="utf-8") as f:
            f.write(value)


def check(nex, root, entry, test_name):
    try:
        child = subprocess.run([str(nex), "test", entry, "--json"], cwd=root,
                               capture_output=True, timeout=90)
        row = json.loads(child.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "TIMEOUT"}
    except ValueError:
        return {"ok": False, "code": "INVALID_REPORT"}
    successes = [s for s in row.get("tests", []) if s.get("name") == test_name
                 and s.get("ok") is True and s.get("native") is True]
    return {"ok": child.returncode == 0 and row.get("ok") is True and len(successes) == 1,
            "code": row.get("code"), "exit": child.returncode}


def verify(root, nex):
    root, nex = Path(root), Path(nex).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="warehouse-oracle-") as folder:
        clean = Path(folder)
        create(clean)
        for name in PROTECTED:
            source = root / name
            if source.is_symlink() or not source.is_file() or source.read_bytes() != (clean / name).read_bytes():
                return {"ok": False, "reason": "protected input changed", "file": name}
        changed = []
        for name in SOURCES:
            source = root / name
            if source.is_symlink() or not source.is_file() or source.stat().st_size > 65536:
                return {"ok": False, "reason": "invalid source", "file": name}
            data = source.read_bytes()
            if data != (clean / name).read_bytes():
                changed.append(name)
            (clean / name).write_bytes(data)
        (clean / "hidden.nex").write_text(held_out(), encoding="utf-8")
        checks = {"visible": check(nex, clean, PROJECT_ENTRY, "warehouse::billing_test::disputed_storage_invoice"),
                  "hidden": check(nex, clean, "hidden.nex", "warehouse::acceptance::hidden_billing_contract")}
        return {"ok": all(v["ok"] for v in checks.values()), "checks": checks,
                "changed_modules": changed, "held_out_cases": len(CASES) - 1}


def preflight(nex):
    with tempfile.TemporaryDirectory(prefix="warehouse-control-") as folder:
        root = Path(folder)
        create(root)
        starter = verify(root, nex)
        path = root / "availability.nex"
        source = path.read_text()
        path.write_text(source.replace("      frontier = event.stop;", "      if frontier < event.stop { frontier = event.stop; }"))
        corrected = verify(root, nex)
        # An end-to-end patch that guesses the disputed invoice must not pass the oracle.
        path.write_text(source)
        api = root / "invoice.nex"
        api.write_text(api.read_text().replace("sales, due);", f"sales, {oracle(VISIBLE)[-1]});"))
        shortcut = verify(root, nex)
        return {"ok": all(not starter["checks"][k]["ok"] and starter["checks"][k]["code"] == "E_ASSERT"
                          for k in ("visible", "hidden")) and corrected["ok"]
                and shortcut["checks"]["visible"]["ok"] and not shortcut["checks"]["hidden"]["ok"],
                "starter": starter, "corrected": corrected, "constant_invoice": shortcut}
