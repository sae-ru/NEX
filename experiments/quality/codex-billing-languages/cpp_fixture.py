"""C++20 translation of the eight NEX billing modules. Only materialized inputs enter the trial."""
VISIBLE_ENTRY = ENTRY = "billing_test.cpp"
HIDDEN_ENTRY = "hidden.cpp"

SOURCES = {
    "models.hpp": """#pragma once
#include <cstdint>

namespace warehouse::models {
using i64 = std::int64_t;
// Rental and outage boundaries are whole days in the same calendar.
struct Period { i64 start, stop; };
struct Rental { Period period; bool climate, member; i64 credit; };
struct Invoice { i64 days, service, discount, tax, due; };
}
""",
    "calendar.hpp": """#pragma once
#include "models.hpp"

namespace warehouse::calendar {
inline models::i64 days(models::Period period) {
    if (period.stop <= period.start) return 0;
    return period.stop - period.start;
}

inline models::Period clip(models::Period period, models::Period rental) {
    auto start = period.start;
    auto stop = period.stop;
    if (start < rental.start) start = rental.start;
    if (stop > rental.stop) stop = rental.stop;
    return {start, stop};
}
}
""",
    "availability.hpp": """#pragma once
#include "calendar.hpp"
#include <vector>

namespace warehouse::availability {
// Source events arrive sorted by start day. Days outside the rental belong
// to other invoices and never reduce this period's availability.
inline models::i64 unavailable(models::Period rental, const std::vector<models::Period>& outages) {
    models::i64 covered = 0;
    auto frontier = rental.start;
    for (const auto& outage : outages) {
        const auto event = calendar::clip(outage, rental);
        if (event.start < event.stop) {
            auto first = event.start;
            if (first < frontier) first = frontier;
            if (first < event.stop) covered += event.stop - first;
            frontier = event.stop;
        }
    }
    return covered;
}
}
""",
    "meter.hpp": """#pragma once
#include "availability.hpp"

namespace warehouse::meter {
inline models::i64 billable(models::Period rental, const std::vector<models::Period>& outages) {
    const auto rented = calendar::days(rental);
    const auto lost = availability::unavailable(rental, outages);
    if (lost >= rented) return 0;
    return rented - lost;
}
}
""",
    "tariff.hpp": """#pragma once
#include "models.hpp"

namespace warehouse::tariff {
inline models::i64 storage(models::i64 days) {
    if (days <= 5) return days * 230;
    return 5 * 230 + (days - 5) * 180;
}
inline models::i64 climate(models::i64 days, bool enabled) {
    return enabled ? days * 35 : 0;
}
inline models::i64 handling(models::i64 days) {
    return days == 0 ? 0 : 125;
}
}
""",
    "benefits.hpp": """#pragma once
#include "models.hpp"

namespace warehouse::benefits {
inline models::i64 discount(models::i64 storage, bool member) {
    return member ? storage / 10 : 0;
}
inline models::i64 balance(models::i64 gross, models::i64 credit) {
    if (credit >= gross) return 0;
    return gross - credit;
}
}
""",
    "tax.hpp": """#pragma once
#include "models.hpp"

namespace warehouse::tax {
// Half-cent rounds up; all amounts are nonnegative cents.
inline models::i64 sales_tax(models::i64 amount) { return (amount + 10) / 20; }
}
""",
    "invoice.hpp": """#pragma once
#include "meter.hpp"
#include "tariff.hpp"
#include "benefits.hpp"
#include "tax.hpp"

namespace warehouse::invoice {
inline models::Invoice quote(models::Rental rental, const std::vector<models::Period>& outages) {
    const auto days = meter::billable(rental.period, outages);
    const auto storage = tariff::storage(days);
    const auto service = storage + tariff::climate(days, rental.climate) + tariff::handling(days);
    const auto rebate = benefits::discount(storage, rental.member);
    const auto sales = tax::sales_tax(service - rebate);
    const auto due = benefits::balance(service - rebate + sales, rental.credit);
    return {days, service, rebate, sales, due};
}
}
""",
}


def _setup(case):
    start, stop, outages, climate, member, credit = case
    flags = f"{str(climate).lower()}, {str(member).lower()}"
    intervals = ", ".join(f"{{{a}, {b}}}" for a, b in outages)
    return f"""    const models::Rental rental{{{{{start}, {stop}}}, {flags}, {credit}}};
    const std::vector<models::Period> events{{{intervals}}};
    const auto statement = invoice::quote(rental, events);
"""


_TEST_HEADER = '''#include "invoice.hpp"
#include <cstdio>
#include <cstdlib>

using namespace warehouse;
static void expect_equal(const char* label, models::i64 actual, models::i64 expected) {
    if (actual != expected) {
        std::fprintf(stderr, "%s: expected %lld, got %lld\\n", label,
                     static_cast<long long>(expected), static_cast<long long>(actual));
        std::exit(1);
    }
}
'''


def visible(shared):
    expected = shared.oracle(shared.VISIBLE)[-1]
    return (_TEST_HEADER + "\nint main() {\n" + _setup(shared.VISIBLE) +
            f'    expect_equal("disputed_storage_invoice: statement.due", statement.due, {expected});\n'
            '    std::puts("passed");\n}\n')


def held_out(shared):
    lines = [_TEST_HEADER]
    for i, case in enumerate(shared.CASES):
        expected = shared.oracle(case)
        lines += [f"static void policy_{i}() {{", _setup(case),
                  f'    expect_equal("unavailable", availability::unavailable(rental.period, events), {case[1]-case[0]-expected[0]});',
                  f'    expect_equal("billable", meter::billable(rental.period, events), {expected[0]});']
        for field, amount in zip(("days", "service", "discount", "tax", "due"), expected):
            lines.append(f'    expect_equal("{field}", statement.{field}, {amount});')
        lines.append("}")
    lines += ["int main() {", *(f"    policy_{i}();" for i in range(len(shared.CASES))),
              '    std::puts("passed");', "}", ""]
    return "\n".join(lines)


def corrected_sources():
    sources = SOURCES.copy()
    key = "availability.hpp"
    sources[key] = sources[key].replace("            frontier = event.stop;",
                                        "            if (frontier < event.stop) frontier = event.stop;")
    return sources
