import os
import time
import unittest
import unittest.mock

from zulip_hub.commands import (
    MAX_OUTPUT_BYTES,
    CommandError,
    resolve,
    run,
)


class ResolveTests(unittest.TestCase):
    def test_a_trusted_executable_resolves_to_an_absolute_path(self):
        found = resolve("sh")
        self.assertTrue(found.startswith("/"))
        self.assertTrue(os.path.isabs(found))

    def test_an_unknown_executable_is_refused(self):
        with self.assertRaises(CommandError):
            resolve("commande-qui-nexiste-pas-du-tout")

    def test_the_inherited_path_cannot_introduce_an_executable(self):
        """Un PATH hérité laisserait un répertoire écrivable primer."""
        with unittest.mock.patch.dict(os.environ, {"PATH": "/tmp/piege"}):
            self.assertTrue(resolve("sh").startswith("/"))


class RunTests(unittest.TestCase):
    def test_output_is_captured_and_the_exit_code_reported(self):
        result = run(["sh", "-c", "printf bonjour"], timeout=10)
        self.assertEqual(result.stdout, "bonjour")
        self.assertEqual(result.returncode, 0)

    def test_standard_input_reaches_the_command(self):
        result = run(["sh", "-c", "cat"], stdin="secret\n", timeout=10)
        self.assertEqual(result.stdout, "secret\n")

    def test_a_failing_command_reports_its_code_without_raising(self):
        result = run(["sh", "-c", "exit 3"], timeout=10)
        self.assertEqual(result.returncode, 3)

    def test_the_environment_is_reduced_to_an_allowlist(self):
        with unittest.mock.patch.dict(os.environ, {"ZULIP_HUB_SECRET_LEAK": "ne-doit-pas-passer"}):
            result = run(["sh", "-c", "env"], timeout=10)
        self.assertNotIn("ZULIP_HUB_SECRET_LEAK", result.stdout)
        self.assertIn("PATH=", result.stdout)

    def test_a_command_that_never_ends_is_killed_at_the_deadline(self):
        started = time.monotonic()
        with self.assertRaises(CommandError):
            run(["sh", "-c", "sleep 30"], timeout=1)
        self.assertLess(time.monotonic() - started, 15)

    def test_a_child_that_outlives_its_parent_is_killed_too(self):
        """La terminaison vise le groupe : un enfant detache survivrait."""
        started = time.monotonic()
        with self.assertRaises(CommandError):
            run(["sh", "-c", "sleep 30 & sleep 30"], timeout=1)
        self.assertLess(time.monotonic() - started, 15)

    def test_a_flood_of_output_is_cut_instead_of_being_accumulated(self):
        started = time.monotonic()
        with self.assertRaises(CommandError):
            run(["sh", "-c", "yes bonjour"], timeout=20)
        self.assertLess(time.monotonic() - started, 20)

    def test_the_output_cap_is_a_real_bound(self):
        self.assertLessEqual(MAX_OUTPUT_BYTES, 4 * 1024 * 1024)


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()
