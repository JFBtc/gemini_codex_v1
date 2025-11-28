import logging
import logging.handlers
import unittest

from ui.dashboard import ModernDashboard, RefreshGuard


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

    def test_safe_refresh_logs_failure(self):
        calls = []

        def failing_refresh():
            calls.append("called")
            raise RuntimeError("Kaboom")

        logger = logging.getLogger("ui.dashboard.test")
        with self.assertLogs(logger, level="ERROR") as cm:
            result = ModernDashboard._safe_refresh("Widget", failing_refresh, logger)

        self.assertFalse(result)
        self.assertEqual(calls, ["called"])
        self.assertIn("Widget", "\n".join(cm.output))

    def test_safe_refresh_can_skip_logging(self):
        def failing_refresh():
            raise RuntimeError("Kaboom")

        logger = logging.getLogger("ui.dashboard.test.skip")
        handler = logging.handlers.BufferingHandler(capacity=10)
        logger.addHandler(handler)
        try:
            result = ModernDashboard._safe_refresh(
                "Widget", failing_refresh, logger, log_exception=False
            )
        finally:
            logger.removeHandler(handler)

        self.assertFalse(result)
        self.assertEqual(handler.buffer, [])


if __name__ == "__main__":
    unittest.main()
