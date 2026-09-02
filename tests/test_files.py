import fcntl
import os
from pathlib import Path
import tempfile
import unittest

from zulip_hub.files import (
    is_managed_module,
    open_directory,
    single_instance,
    write_exclusive,
    write_no_follow,
)


class ManagedModuleTests(unittest.TestCase):
    """Un lien symbolique au chemin du module ferait ecrire ailleurs."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.module = self.directory / "zulip_hub.lua"

    def tearDown(self):
        self.temporary.cleanup()

    def test_an_absent_path_is_free_to_use(self):
        self.assertTrue(is_managed_module(self.module))

    def test_a_file_we_wrote_is_recognised(self):
        self.module.write_text("-- Omarchy Zulip Hub\n", encoding="utf-8")
        self.assertTrue(is_managed_module(self.module))

    def test_a_symlink_is_never_treated_as_ours(self):
        target = self.directory / "cible.lua"
        target.write_text("-- Omarchy Zulip Hub\n", encoding="utf-8")
        self.module.symlink_to(target)
        self.assertFalse(is_managed_module(self.module))

    def test_a_dangling_symlink_is_not_mistaken_for_an_absent_file(self):
        self.module.symlink_to(self.directory / "nulle-part.lua")
        self.assertFalse(is_managed_module(self.module))

    def test_a_directory_is_never_treated_as_ours(self):
        self.module.mkdir()
        self.assertFalse(is_managed_module(self.module))


class ParentDirectoryTests(unittest.TestCase):
    """Protéger le seul dernier segment laisse écrire à travers un parent
    remplacé par un lien."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.real = self.base / "ailleurs"
        self.real.mkdir()
        (self.real / "zulip_hub.lua").write_text("intact", encoding="utf-8")
        self.link = self.base / "hypr"
        self.link.symlink_to(self.real)

    def tearDown(self):
        self.temporary.cleanup()

    def test_writing_through_a_symlinked_parent_is_refused(self):
        with self.assertRaises(OSError):
            write_no_follow(self.link / "zulip_hub.lua", b"traverse")
        self.assertEqual((self.real / "zulip_hub.lua").read_text(encoding="utf-8"), "intact")

    def test_creating_through_a_symlinked_parent_is_refused(self):
        with self.assertRaises(OSError):
            write_exclusive(self.link / "nouveau.lua", b"traverse")
        self.assertFalse((self.real / "nouveau.lua").exists())

    def test_a_real_parent_still_works(self):
        write_no_follow(self.real / "zulip_hub.lua", b"remplace")
        self.assertEqual((self.real / "zulip_hub.lua").read_text(encoding="utf-8"), "remplace")

    def test_a_directory_walk_refuses_a_symlinked_component(self):
        with self.assertRaises(OSError):
            descriptor = open_directory(self.base, "hypr")
            os.close(descriptor)

    def test_a_directory_walk_accepts_real_components(self):
        descriptor = open_directory(self.base, "ailleurs")
        try:
            self.assertGreaterEqual(descriptor, 0)
        finally:
            os.close(descriptor)


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
