import logging
import unittest

from ui.dashboard import RefreshGuard


class RefreshGuardTests(unittest.TestCase):
    def test_logs_and_counts_failure(self):
        guard = RefreshGuard()

        with self.assertLogs(level="ERROR") as cm:
            try:
                raise RuntimeError("Boom")
            except RuntimeError:
                suffix = guard.record_failure("ExecutionView")

        self.assertEqual(guard.failure_count, 1)
        self.assertEqual(suffix, " ⚠️ (1)")
        joined_logs = "\n".join(cm.output)
        self.assertIn("ExecutionView", joined_logs)
        self.assertIn("Boom", joined_logs)

    def test_success_resets_counter(self):
        guard = RefreshGuard()
        try:
            raise RuntimeError("Boom")
        except RuntimeError:
            guard.record_failure("ExecutionView")

        suffix = guard.record_success()

        self.assertEqual(guard.failure_count, 0)
        self.assertEqual(suffix, "")
        self.assertEqual(guard.status_suffix, "")


if __name__ == "__main__":
    unittest.main()
