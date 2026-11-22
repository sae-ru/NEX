"""Python port of the Depot Ledger fixture; the controller supplies the common oracle."""
VISIBLE_ENTRY = "billing_test.py"
HIDDEN_ENTRY = "hidden.py"

SOURCES = {
    "models.py": '''"""Rental and outage boundaries are whole days in the same calendar."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Period:
    start: int
    stop: int


@dataclass(frozen=True)
class Rental:
    period: Period
    climate: bool
    member: bool
    credit: int


@dataclass(frozen=True)
class Invoice:
    days: int
    service: int
    discount: int
    tax: int
    due: int
''',
    "calendar_ops.py": '''from models import Period


def days(period: Period) -> int:
    return max(0, period.stop - period.start)


def clip(period: Period, rental: Period) -> Period:
    return Period(max(period.start, rental.start), min(period.stop, rental.stop))
''',
    "availability.py": '''import calendar_ops
from models import Period


def unavailable(rental: Period, outages: list[Period]) -> int:
    """Count unavailable days within the rental; outages arrive sorted by start."""
    covered = 0
    frontier = rental.start
    for outage in outages:
        event = calendar_ops.clip(outage, rental)
        if event.start < event.stop:
            first = max(event.start, frontier)
            if first < event.stop:
                covered += event.stop - first
            frontier = event.stop
    return covered
''',
    "meter.py": '''import availability
import calendar_ops
from models import Period


def billable(rental: Period, outages: list[Period]) -> int:
    rented = calendar_ops.days(rental)
    lost = availability.unavailable(rental, outages)
    return max(0, rented - lost)
''',
    "tariff.py": '''def storage(days: int) -> int:
    if days <= 5:
        return days * 230
    return 5 * 230 + (days - 5) * 180


def climate(days: int, enabled: bool) -> int:
    return days * 35 if enabled else 0


def handling(days: int) -> int:
    return 0 if days == 0 else 125
''',
    "benefits.py": '''def discount(storage: int, member: bool) -> int:
    return storage // 10 if member else 0


def balance(gross: int, credit: int) -> int:
    return max(0, gross - credit)
''',
    "tax.py": '''def sales_tax(amount: int) -> int:
    """Half-cent rounds up; all amounts are nonnegative cents."""
    return (amount + 10) // 20
''',
    "invoice.py": '''import benefits
import meter
import tariff
import tax
from models import Invoice, Period, Rental


def quote(rental: Rental, outages: list[Period]) -> Invoice:
    days = meter.billable(rental.period, outages)
    storage = tariff.storage(days)
    service = storage + tariff.climate(days, rental.climate) + tariff.handling(days)
    rebate = benefits.discount(storage, rental.member)
    sales = tax.sales_tax(service - rebate)
    due = benefits.balance(service - rebate + sales, rental.credit)
    return Invoice(days, service, rebate, sales, due)
''',
}


def _expressions(case):
    start, stop, outages, climate, member, credit = case
    period = f"Period({start}, {stop})"
    events = "[" + ", ".join(f"Period({a}, {b})" for a, b in outages) + "]"
    return period, f"Rental({period}, {climate}, {member}, {credit})", events


def visible(common):
    _, rental, events = _expressions(common.VISIBLE)
    expected = common.oracle(common.VISIBLE)[-1]
    return f'''import invoice
from models import Period, Rental


def disputed_storage_invoice():
    rental = {rental}
    events = {events}
    statement = invoice.quote(rental, events)
    assert statement.due == {expected}, f"expected {expected}, got {{statement.due}}"


if __name__ == "__main__":
    disputed_storage_invoice()
'''


def held_out(common):
    code = ["import availability", "import invoice", "import meter",
            "from models import Invoice, Period, Rental", ""]
    for case in common.CASES:
        period, rental, events = _expressions(case)
        expected = common.oracle(case)
        unavailable = case[1] - case[0] - expected[0]
        code.extend([
            f"events = {events}",
            f"assert availability.unavailable({period}, events) == {unavailable}",
            f"assert meter.billable({period}, events) == {expected[0]}",
            f"assert invoice.quote({rental}, events) == Invoice{expected!r}",
            "",
        ])
    return "\n".join(code)
