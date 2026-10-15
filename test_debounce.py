"""Host-side behavioral checks for the firmware stable-level debounce rule."""
import unittest


class StableDebouncer:
    def __init__(self, debounce_us, initial=False):
        self.debounce_us = debounce_us
        self.raw = initial
        self.stable = initial
        self.changed_at = 0

    def scan(self, value, now):
        if value != self.raw:
            self.raw = value
            self.changed_at = now
        if self.raw != self.stable and (
            self.debounce_us == 0 or now - self.changed_at >= self.debounce_us
        ):
            self.stable = self.raw
            return self.stable
        return None


class DebounceTests(unittest.TestCase):
    def test_short_press_and_release(self):
        d = StableDebouncer(1000)
        self.assertIsNone(d.scan(True, 10))
        self.assertTrue(d.scan(True, 1010))
        self.assertIsNone(d.scan(False, 1100))
        self.assertFalse(d.scan(False, 2100))

    def test_bounce_restarts_timer_and_accepts_final_level(self):
        d = StableDebouncer(1000)
        self.assertIsNone(d.scan(True, 10))
        self.assertIsNone(d.scan(False, 400))
        self.assertIsNone(d.scan(True, 700))
        self.assertIsNone(d.scan(True, 1699))
        self.assertTrue(d.scan(True, 1700))

    def test_fast_repeated_taps(self):
        d = StableDebouncer(500)
        self.assertIsNone(d.scan(True, 0))
        self.assertTrue(d.scan(True, 500))
        self.assertIsNone(d.scan(False, 600))
        self.assertFalse(d.scan(False, 1100))
        self.assertIsNone(d.scan(True, 1200))
        self.assertTrue(d.scan(True, 1700))

    def test_zero_is_direct(self):
        d = StableDebouncer(0)
        self.assertTrue(d.scan(True, 12))
        self.assertFalse(d.scan(False, 13))


if __name__ == "__main__":
    unittest.main()
