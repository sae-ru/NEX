import unittest

from compare import BLOCKS, COMMON_PINS, LANGUAGE_PINS, compare


def samples():
    rows = []
    for block, order in enumerate(BLOCKS, 1):
        for pos, lang in enumerate(order, 1):
            in_tokens = {"nex": 120, "cpp": 60, "python": 40}[lang]
            row = dict.fromkeys((*COMMON_PINS,*LANGUAGE_PINS), "a"*64)
            row.update(language=lang, block=block, position=pos, model="test-model",
                       started_utc=f"2026-11-23T{3*(block-1)+pos:02d}:00:00+00:00",
                       status="finished", accepted=True, acceptance={"ok": True, "checks": {
                       "visible": {"ok": True, "exit": 0}, "hidden": {"ok": True, "exit": 0}}},
                       agent_seconds=10, end_to_end_seconds=13, raw_sha256="a"*64,
                       usage={"input_tokens": in_tokens, "cached_input_tokens": 40, "output_tokens": 20,
                              "reasoning_output_tokens": 2})
            rows.append(row)
    return rows


class Accounting(unittest.TestCase):
    def test_metering_and_ratios_include_cost_of_failure(self):
        rows = samples()
        rows[0].update(accepted=False, acceptance={"ok": False, "checks": {"hidden": {"ok": False}}})
        r = compare(rows[::-1])
        nex = r["languages"]["nex"]
        self.assertEqual(nex["accepted"], 2)
        self.assertAlmostEqual(nex["input_cache_share"], 1/3, places=6)
        m = nex["metrics"]
        self.assertEqual(m["total_tokens"]["per_accepted"], 210)
        self.assertEqual(m["total_tokens"]["total"], 420)
        self.assertEqual(m["uncached_input_plus_output"]["per_accepted"], 150)
        self.assertEqual(m["end_to_end_seconds"]["per_accepted"], 19.5)
        self.assertEqual(r["per_accepted_ratios"]["nex_over_cpp"]["total_tokens"], 210 / 80)
        self.assertIsNone(r["currency_cost"])

    def test_missing_usage_cache_or_no_accepted_results(self):
        rows = samples()
        rows[0]["usage"].pop("cached_input_tokens")
        m = compare(rows)["languages"]["nex"]["metrics"]
        self.assertEqual(m["uncached_input_plus_output"]["observed_trials"], 2)
        self.assertIsNone(m["uncached_input_plus_output"]["per_accepted"])
        self.assertEqual(m["total_tokens"]["per_accepted"], 140)
        rows[0]["usage"] = None
        for row in rows:
            if row["language"] == "cpp":
                row.update(accepted=False, acceptance={"ok": False})
        r = compare(rows)
        self.assertEqual(r["languages"]["nex"]["metrics"]["total_tokens"]["observed_sum"], 280)
        self.assertIsNone(r["languages"]["nex"]["metrics"]["total_tokens"]["total"])
        self.assertIsNone(r["languages"]["cpp"]["metrics"]["end_to_end_seconds"]["per_accepted"])
        self.assertIsNone(r["per_accepted_ratios"]["nex_over_cpp"]["total_tokens"])

    def test_order_pin_cache_and_acceptance_guards(self):
        rows = samples()
        for row in rows:
            if row["language"] == "cpp":
                row["full_prompt_sha256"] = "e"*64
        with self.assertRaisesRegex(ValueError, "common task or tool identity"):
            compare(rows)
        for patch in ({"language":"cpp"}, {"block":True}, {"runner_sha256":"b"*64},
                      {"starter_sha256":"d"*64}, {"toolchain_sha256":"0"*64}, {"status":"running"},
                      {"usage":{"input_tokens":2, "cached_input_tokens":3, "output_tokens":2}},
                      {"usage":{"input_tokens":False, "output_tokens":5}}, {"accepted":False},
                      {"agent_seconds":14}, {"end_to_end_seconds":float("nan")},
                      {"started_utc":"2026-11-23T12:00:00+00:00"},
                      {"acceptance":{"ok":True,"checks":{"visible":{"ok":True}}}}):
            rows = samples()
            rows[0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                compare(rows)
        with self.assertRaises(ValueError):
            compare(samples()[:-1])
        rows = samples()
        with self.assertRaises(ValueError):
            compare([*rows[1:], rows[-1]])


if __name__ == "__main__":
    unittest.main()
