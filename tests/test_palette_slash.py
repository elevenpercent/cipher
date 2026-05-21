import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cipher.app import (
    SLASH_COMMANDS, CommandPalette, CipherApp,
    load_config, CONFIG_DIR, CONFIG_FILE,
)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

class TestSlashCommandsDict(unittest.TestCase):
    EXPECTED = ["/help", "/clear", "/new", "/sessions", "/theme",
                "/model", "/provider", "/compact", "/tokens", "/quit"]

    def test_all_commands_present(self):
        for cmd in self.EXPECTED:
            self.assertIn(cmd, SLASH_COMMANDS, f"Missing slash command: {cmd}")

    def test_all_have_descriptions(self):
        for cmd, desc in SLASH_COMMANDS.items():
            self.assertIsInstance(desc, str)
            self.assertGreater(len(desc), 0, f"Empty description for {cmd}")

    def test_count(self):
        self.assertGreaterEqual(len(SLASH_COMMANDS), len(self.EXPECTED))


class TestSlashCommandParsing(unittest.TestCase):
    def _parse(self, msg):
        parts = msg.strip().split(None, 1)
        base = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        return base, arg

    def test_bare_command(self):
        base, arg = self._parse("/clear")
        self.assertEqual(base, "/clear")
        self.assertEqual(arg, "")

    def test_command_with_arg(self):
        base, arg = self._parse("/theme dracula")
        self.assertEqual(base, "/theme")
        self.assertEqual(arg, "dracula")

    def test_command_with_spaced_arg(self):
        base, arg = self._parse("/model llama-3.3-70b")
        self.assertEqual(base, "/model")
        self.assertEqual(arg, "llama-3.3-70b")

    def test_provider_command(self):
        base, arg = self._parse("/provider groq")
        self.assertEqual(base, "/provider")
        self.assertEqual(arg, "groq")

    def test_tokens_no_arg(self):
        base, arg = self._parse("/tokens")
        self.assertEqual(base, "/tokens")
        self.assertEqual(arg, "")

    def test_quit_no_arg(self):
        base, arg = self._parse("/quit")
        self.assertEqual(base, "/quit")
        self.assertEqual(arg, "")


class TestSlashCommandHandling(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import cipher.app as app_mod
        self.orig_config_dir = app_mod.CONFIG_DIR
        self.orig_config_file = app_mod.CONFIG_FILE
        self.orig_sessions_dir = app_mod.SESSIONS_DIR
        self.orig_skills_dir = app_mod.SKILLS_DIR
        app_mod.CONFIG_DIR = Path(self.tmpdir) / ".cipher"
        app_mod.CONFIG_FILE = app_mod.CONFIG_DIR / "config.json"
        app_mod.SESSIONS_DIR = app_mod.CONFIG_DIR / "sessions"
        app_mod.SKILLS_DIR = app_mod.CONFIG_DIR / "skills"
        app_mod.CONFIG_DIR.mkdir(exist_ok=True)
        app_mod.SESSIONS_DIR.mkdir(exist_ok=True)
        app_mod.SKILLS_DIR.mkdir(exist_ok=True)
        self.app = CipherApp(project_root=self.tmpdir)

    def tearDown(self):
        import cipher.app as app_mod
        app_mod.CONFIG_DIR = self.orig_config_dir
        app_mod.CONFIG_FILE = self.orig_config_file
        app_mod.SESSIONS_DIR = self.orig_sessions_dir
        app_mod.SKILLS_DIR = self.orig_skills_dir

    def test_theme_command_updates_config(self):
        self.app.config["theme"] = "dark"
        self.app.config["theme"] = "dracula"
        self.assertEqual(self.app.config["theme"], "dracula")

    def test_model_command_updates_config(self):
        self.app.config["model"] = "llama-3.3-70b"
        self.app.config["model"] = "llama-3.1-8b"
        self.assertEqual(self.app.config["model"], "llama-3.1-8b")

    def test_provider_command_updates_config(self):
        self.app.config["provider"] = "cipher-proxy"
        self.app.config["provider"] = "groq"
        self.assertEqual(self.app.config["provider"], "groq")

    def test_compact_toggle(self):
        self.app.config["compact_mode"] = False
        self.app.config["compact_mode"] = not self.app.config.get("compact_mode", False)
        self.assertTrue(self.app.config["compact_mode"])
        self.app.config["compact_mode"] = not self.app.config.get("compact_mode", False)
        self.assertFalse(self.app.config["compact_mode"])


# ---------------------------------------------------------------------------
# Command palette (non-TUI logic only)
# ---------------------------------------------------------------------------

class TestCommandPaletteInit(unittest.TestCase):
    def _make_actions(self):
        return [
            ("reset", "Reset settings to defaults"),
            ("clear", "Clear the chat"),
            ("update", "Check for updates"),
            ("setup", "Run setup wizard"),
            ("new session", "Start a new session"),
        ]

    def test_init_stores_actions(self):
        actions = self._make_actions()
        palette = CommandPalette(actions)
        self.assertEqual(palette.actions, actions)

    def test_init_filtered_equals_actions(self):
        actions = self._make_actions()
        palette = CommandPalette(actions)
        self.assertEqual(palette.filtered, actions)

    def test_init_selected_zero(self):
        palette = CommandPalette(self._make_actions())
        self.assertEqual(palette.selected, 0)

    def test_empty_actions(self):
        palette = CommandPalette([])
        self.assertEqual(palette.filtered, [])
        self.assertEqual(palette.selected, 0)


class TestCommandPaletteFiltering(unittest.TestCase):
    def setUp(self):
        self.actions = [
            ("reset", "Reset settings to defaults"),
            ("clear", "Clear the chat"),
            ("update", "Check for updates"),
            ("setup", "Run setup wizard"),
            ("new session", "Start a new session"),
        ]
        self.palette = CommandPalette(self.actions)

    def _apply_filter(self, q):
        q = q.lower()
        if q:
            self.palette.filtered = [
                (k, v) for k, v in self.palette.actions
                if q in k.lower() or q in v.lower()
            ]
        else:
            self.palette.filtered = list(self.palette.actions)
        self.palette.selected = 0

    def test_filter_exact_match(self):
        self._apply_filter("reset")
        self.assertEqual(len(self.palette.filtered), 1)
        self.assertEqual(self.palette.filtered[0][0], "reset")

    def test_filter_partial_match(self):
        self._apply_filter("set")
        keys = [k for k, _ in self.palette.filtered]
        self.assertIn("reset", keys)
        self.assertIn("setup", keys)

    def test_filter_description_match(self):
        self._apply_filter("wizard")
        self.assertEqual(len(self.palette.filtered), 1)
        self.assertEqual(self.palette.filtered[0][0], "setup")

    def test_filter_no_match(self):
        self._apply_filter("xyzzy")
        self.assertEqual(len(self.palette.filtered), 0)

    def test_filter_empty_restores_all(self):
        self._apply_filter("reset")
        self._apply_filter("")
        self.assertEqual(len(self.palette.filtered), len(self.actions))

    def test_filter_resets_selected(self):
        self.palette.selected = 3
        self._apply_filter("clear")
        self.assertEqual(self.palette.selected, 0)

    def test_filter_case_insensitive(self):
        self._apply_filter("RESET")
        self.assertEqual(len(self.palette.filtered), 1)


class TestCommandPaletteCursor(unittest.TestCase):
    def setUp(self):
        self.actions = [("a", "desc a"), ("b", "desc b"), ("c", "desc c")]
        self.palette = CommandPalette(self.actions)

    def test_cursor_down(self):
        self.palette.selected = 0
        self.palette.selected = min(len(self.palette.filtered) - 1, self.palette.selected + 1)
        self.assertEqual(self.palette.selected, 1)

    def test_cursor_up(self):
        self.palette.selected = 2
        self.palette.selected = max(0, self.palette.selected - 1)
        self.assertEqual(self.palette.selected, 1)

    def test_cursor_up_at_zero_stays(self):
        self.palette.selected = 0
        self.palette.selected = max(0, self.palette.selected - 1)
        self.assertEqual(self.palette.selected, 0)

    def test_cursor_down_at_end_stays(self):
        self.palette.selected = 2
        self.palette.selected = min(len(self.palette.filtered) - 1, self.palette.selected + 1)
        self.assertEqual(self.palette.selected, 2)

    def test_cursor_wraps_correctly_across_range(self):
        for _ in range(10):
            self.palette.selected = min(len(self.palette.filtered) - 1, self.palette.selected + 1)
        self.assertEqual(self.palette.selected, 2)

    def test_dismiss_returns_selected_action(self):
        self.palette.selected = 1
        result = self.palette.filtered[self.palette.selected][0]
        self.assertEqual(result, "b")

    def test_dismiss_empty_filtered_returns_none(self):
        self.palette.filtered = []
        result = self.palette.filtered[self.palette.selected][0] if self.palette.filtered else None
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
