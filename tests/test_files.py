import fcntl
from pathlib import Path
import tempfile
import unittest

from zulip_hub.files import single_instance


class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.lock = Path(self.temporary.name) / "bridge.lock"

    def tearDown(self):
        self.temporary.cleanup()

    def _held_by_someone_else(self) -> bool:
        with open(self.lock, "a", encoding="utf-8") as other:
            try:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(other, fcntl.LOCK_UN)
            return False

    def test_a_second_bridge_cannot_take_the_lock_while_one_runs(self):
        with single_instance(self.lock):
            self.assertTrue(self._held_by_someone_else())

    def test_the_lock_is_released_when_the_bridge_stops(self):
        with single_instance(self.lock):
            pass
        self.assertFalse(self._held_by_someone_else())

    def test_the_lock_is_released_even_when_the_bridge_crashes(self):
        with self.assertRaises(RuntimeError):
            with single_instance(self.lock):
                raise RuntimeError("le bridge sest arrete")
        self.assertFalse(self._held_by_someone_else())

    def test_the_lock_file_is_created_with_its_parent_directory(self):
        nested = self.lock.parent / "state" / "bridge.lock"
        with single_instance(nested):
            self.assertTrue(nested.exists())


if __name__ == "__main__":
    unittest.main()
