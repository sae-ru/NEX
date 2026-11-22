import unittest

import compare as campaign


def samples():
    rows = []
    for task in campaign.TASKS:
        for arm in campaign.ARMS:
            checks = {key: {"ok": True, "exit": 0, "native": True}
                      for key in campaign.CHECK_NAMES.get(task, ("visible", "held_out"))}
            row = dict.fromkeys(("fixtures_sha256", "runner_sha256", "cli_sha256", "prompt_sha256",
                                 "guide_sha256", "nex_sha256", "raw_sha256"), "a" * 64)
            row.update(schema="nex.codex-maintenance/1", arm=arm, task=task, cli="codex-cli 1.0",
                       cli_options=["--setting=/private/private-account/dir"], model="test-model",
                       status="finished", timeout_seconds=60, unchanged_sdk=True, source_commit="b" * 40,
                       starter_sha256={"main.nex": "a" * 64}, accepted=True, complete_usage=True,
                       usage={"input_tokens": 100 if arm == "before" else 60, "output_tokens": 20,
                              "cached_input_tokens": 40}, agent_seconds=1.25, end_to_end_seconds=2.03,
                       acceptance={"ok": True, "checks": checks}, events={"turn.completed": 1},
                       timed_out=False, exit_code=0)
            rows.append(row)
    return rows


class Comparison(unittest.TestCase):
    def test_failures_are_charged_and_caches_are_subsets(self):
        rows = samples()
        failed = rows[0]
        failed.update(accepted=False, acceptance={"ok": False, "reason": "changed immutable input"})
        result = campaign.compare(rows)
        before = result["arms"]["before"]
        self.assertEqual(before["accepted"], 2)
        self.assertEqual(before["metrics"]["total_tokens"]["total"], 360)
        self.assertEqual(before["metrics"]["uncached_input_tokens"]["total"], 180)
        self.assertEqual(before["metrics"]["total_tokens"]["per_accepted"], 180)
        self.assertEqual(result["savings"]["total_tokens"]["total"], {"saved": 120, "percent": 33.333})
        self.assertEqual(before["metrics"]["end_to_end_ms"]["total"], 6090)
        self.assertNotIn("private-account", str(result))

    def test_incomplete_usage_preserves_observed_tokens_and_wall_time(self):
        rows = samples()
        rows[-1].update(usage=None, complete_usage=False)
        result = campaign.compare(rows)
        after = result["arms"]["after"]["metrics"]
        self.assertEqual(after["total_tokens"], {"observed_trials": 2, "known_sum": 160,
                                                "total": None, "per_accepted": None})
        self.assertIsNone(result["savings"]["total_tokens"]["total"]["saved"])
        self.assertEqual(result["savings"]["agent_ms"]["total"]["saved"], 0)

    def test_wrong_pair_duplicate_or_changed_compiler(self):
        rows = samples()
        for key in ("runner_sha256", "prompt_sha256", "nex_sha256", "cli_sha256", "fixtures_sha256"):
            changed = dict(rows[0], **{key: "d" * 64})
            with self.subTest(key=key), self.assertRaises(ValueError):
                campaign.compare([changed, *rows[1:]])
        with self.assertRaises(ValueError):
            campaign.compare(rows[:-1])
        with self.assertRaises(ValueError):
            campaign.compare([rows[0], *rows[:-1]])


if __name__ == "__main__":
    unittest.main()
