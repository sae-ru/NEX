import unittest

from compare import BLOCKS, PINS, compare


def samples():
    rows = []
    for b, arms in enumerate(BLOCKS, 1):
        for p, arm in enumerate(arms, 1):
            # Cost is 100 baseline with 20 saved by context, 15 by diagnostics
            # and a further 5 when combined. A block-wide shift preserves effects.
            cost = {"old": 100, "context": 80, "diagnostic": 85, "both": 60}[arm] + (b-1)*10
            r = dict.fromkeys(PINS, "1" * 64)
            r.update(schema="nex.codex-multimodule/1", status="finished", unchanged_sdks=True, exit_code=0,
                     events={"turn.completed": 1}, timed_out=False, complete_usage=True,
                     acceptance={"ok": True, "checks": {"visible": {"ok": True, "exit": 0},
                                                        "hidden": {"ok": True, "exit": 0}}},
                     source_commit="a"*40, cli_version="codex-cli 1.0", timeout_seconds=60,
                     new_sha256="2"*64, raw_sha256="4"*64, full_prompt_sha256="3"*64,
                     context_sha256=("c" if arm in ("both","context") else "0")*64,
                     diagnostic_sha256=("d" if arm in ("both","diagnostic") else "0")*64,
                     started_utc=f"2026-11-22T{4*(b-1)+p:02d}:00:00+00:00", block=b, position=p, arm=arm, accepted=True, model="model", agent_seconds=cost,
                     end_to_end_seconds=cost+1, usage={"input_tokens": cost-10,
                                                     "cached_input_tokens": 40, "output_tokens": 10},
                     exposure={"context_bytes": 15 if arm in ("context", "both") else 100,
                               "diagnostic_bytes": 55 if arm in ("diagnostic", "both") else 8})
            rows.append(r)
    return rows


class FactorComparison(unittest.TestCase):
    def test_conditional_marginal_interaction_and_denominators(self):
        r = compare(samples()[::-1])
        e = r["effects"]
        self.assertEqual(e["both_vs_old"]["total_tokens"], {"saved": 40.0, "percent": 38.0952})
        self.assertEqual(e["context_without_diagnostic"]["total_tokens"]["saved"], 20)
        self.assertEqual(e["context_with_diagnostic"]["total_tokens"]["saved"], 25)
        self.assertEqual(e["context_main_effect"]["total_tokens"]["saved"], 22.5)
        self.assertEqual(e["diagnostic_main_effect"]["end_to_end_seconds"]["saved"], 17.5)
        self.assertEqual(e["interaction_extra_saved"]["total_tokens"], 5)
        self.assertEqual(r["effects_by_block"]["1"]["both_vs_old"]["total_tokens"]["percent"], 40)

    def test_missing_cache_and_failed_trial(self):
        rows = samples()
        rows[0].update(accepted=False, acceptance={"ok": False, "checks": {"hidden": {"ok": False, "exit": 1}}})
        rows[0]["usage"]["cached_input_tokens"] = None
        r = compare(rows)
        self.assertFalse(r["all_accepted"])
        self.assertEqual(r["arms"]["old"]["metrics"]["total_tokens"]["per_accepted"], 210)
        self.assertIsNone(r["effects"]["both_vs_old"]["uncached_input_tokens"]["saved"])
        rows[0].update(usage=None, complete_usage=False)
        r = compare(rows)
        self.assertEqual(r["arms"]["old"]["metrics"]["total_tokens"]["observed_sum"], 110)
        self.assertIsNone(r["effects"]["both_vs_old"]["total_tokens"]["saved"])
        self.assertEqual(r["effects"]["context_with_diagnostic"]["total_tokens"]["saved"], 25)

    def test_reject_wrong_order_inputs_and_uncontrolled_feature_packets(self):
        for attr, val in (("position", 2), ("fixture_sha256", "2"*64), ("accepted", "false"),
                          ("started_utc", "2026-11-22T08:00:00+00:00"), ("new_sha256", "f"*64), ("context_sha256", "a"*64), ("unchanged_sdks", False),
                          ("acceptance", {"ok": True, "checks": {"visible": {"ok": True, "exit": 1}}}),
                          ("exposure", {"context_bytes": 99, "diagnostic_bytes": 8}),
                          ("usage", {"input_tokens": 1, "output_tokens": 1, "cached_input_tokens": 2})):
            rows = samples()
            rows[0][attr] = val
            with self.subTest(attr=attr), self.assertRaises(ValueError):
                compare(rows)


if __name__ == "__main__":
    unittest.main()
