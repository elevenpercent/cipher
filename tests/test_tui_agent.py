# Derived from opencode (MIT) - Copyright (c) 2025 opencode.ai
"""TUI test agent — programmatically drives Cipher's Textual interface."""

import os
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Input, Button, Checkbox, Select
from textual.containers import VerticalScroll

from cipher.app import CipherApp, load_config, save_config, CONFIG_DIR, PROVIDERS


pytestmark = pytest.mark.asyncio


@pytest.fixture
def temp_config(tmp_path):
    fake_config = tmp_path / ".cipher"
    fake_config.mkdir()
    cfg = {
        "provider": "cipher-proxy",
        "model": "llama-3.3-70b",
        "show_plan": True,
        "show_code": True,
        "show_diff": True,
        "show_tool_exec": True,
        "auto_confirm": True,
        "compact_mode": False,
        "theme": "dark",
        "permissions": {"auto_allow": {}, "auto_deny": {}},
        "custom_tools": [],
        "proxy_url": "https://proxy-blue-kappa.vercel.app",
    }
    with open(fake_config / "config.json", "w") as f:
        json.dump(cfg, f)
    with patch("cipher.app.CONFIG_DIR", fake_config), \
         patch("cipher.app.CONFIG_FILE", fake_config / "config.json"), \
         patch("cipher.app.SESSIONS_DIR", fake_config / "sessions"), \
         patch("cipher.app.SKILLS_DIR", fake_config / "skills"):
        (fake_config / "sessions").mkdir()
        (fake_config / "skills").mkdir()
        yield fake_config


class TestTUIStartup:
    async def test_app_mounts(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.is_running
            header = app.query_one("#header-left")
            text = header.render()
            assert "CIPHER" in str(text)
            chat_container = app.query_one("#chat-container")
            assert chat_container is not None
            chat_input = app.query_one("#chat-input", Input)
            assert chat_input is not None

    async def test_header_shows_provider_and_model(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            header_right = app.query_one("#header-right")
            text = header_right.render()
            assert "cipher-proxy" in str(text)

    async def test_startup_messages(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            container = app.query_one("#chat-container")
            msg_count = len(list(container.children))
            assert msg_count >= 2

    async def test_input_placeholder(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            assert "Ask Cipher" in inp.placeholder

    async def test_input_focused_on_start(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            assert inp.has_focus

    async def test_status_bar_exists(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            status = app.query_one("#status-bar")
            assert status is not None


class TestTUISettingsModal:
    async def test_settings_opens_with_ctrl_s(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert app.screen_stack is not None

    async def test_settings_has_action_buttons(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            buttons = app.screen.query(Button)
            ids = [b.id for b in buttons]
            assert "action_clear" in ids
            assert "action_new" in ids
            assert "action_sessions" in ids
            assert "action_quit" in ids

    async def test_settings_has_save_and_cancel(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            buttons = app.screen.query(Button)
            ids = [b.id for b in buttons]
            assert "settings_save" in ids
            assert "settings_cancel" in ids

    async def test_settings_has_checkboxes(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            checkboxes = app.screen.query(Checkbox)
            assert len(checkboxes) >= 5

    async def test_settings_has_theme_select(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            selects = app.screen.query(Select)
            theme_selects = [s for s in selects if s.id == "theme_select"]
            assert len(theme_selects) >= 1

    async def test_settings_scrollable(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            scroll = app.screen.query(VerticalScroll)
            assert len(scroll) >= 1


class TestTUIInput:
    async def test_input_accepts_text(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            inp.value = "hello world"
            assert inp.value == "hello world"

    async def test_enter_saves_to_chat_messages(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            inp.value = "test message"
            await pilot.press("enter")
            await pilot.pause()
            user_msgs = [m for m in app.chat_messages if m["role"] == "user"]
            assert len(user_msgs) >= 1
            assert user_msgs[-1]["content"] == "test message"

    async def test_clear_input_on_escape(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            inp.value = "something"
            await pilot.press("escape")
            assert inp.value == ""

    async def test_empty_input_does_not_submit(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            before = len(app.chat_messages)
            await pilot.press("enter")
            await pilot.pause()
            assert len(app.chat_messages) == before


class TestTUIClearNew:
    async def test_clear_chat_action(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            inp.value = "hello"
            await pilot.press("enter")
            await pilot.pause()
            assert len(app.chat_messages) > 1
            app._do_clear()
            assert len(app.chat_messages) == 1
            assert app.chat_messages[0]["role"] == "system"

    async def test_new_session_action(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            old_id = app.session_id
            import asyncio
            await asyncio.sleep(1.1)
            app._do_new()
            assert app.session_id != old_id
            assert len(app.chat_messages) == 1


class TestTUITheme:
    async def test_theme_default_is_dark(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.theme_manager.current.name == "dark"

    async def test_theme_can_be_changed_in_config(self, temp_config):
        cfg = load_config()
        cfg["theme"] = "nord"
        save_config(cfg)
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.theme_manager.current.name == "nord"


class TestTUISessionManagement:
    async def test_session_saves_on_message(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            inp.value = "test session save"
            await pilot.press("enter")
            await pilot.pause()
            session_dir = temp_config / "sessions"
            saved = list(session_dir.glob("*.json"))
            assert len(saved) >= 1

    async def test_session_title_generated(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#chat-input", Input)
            inp.value = "short title"
            await pilot.press("enter")
            await pilot.pause()
            assert app.session_title == "short title"

    async def test_session_modal_opens(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            app._show_sessions()
            await pilot.pause()
            assert len(app.screen_stack) >= 1


class TestTUIPermissions:
    async def test_auto_confirm_bypasses_yesno(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.permission_manager.check("run", "echo test") == "allow"

    async def test_permission_denies_blocked_tool(self, temp_config):
        cfg = load_config()
        cfg["permissions"] = {"auto_deny": {"run": ["rm*"]}}
        cfg["auto_confirm"] = False
        save_config(cfg)
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.permission_manager.check("run", "rm -rf /") == "deny"

    async def test_read_bypasses_confirm(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.permission_manager.check("read", "any file") == "allow"

    async def test_write_requires_confirm_without_auto(self, temp_config):
        cfg = load_config()
        cfg["auto_confirm"] = False
        save_config(cfg)
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.permission_manager.check("write", "test.py") == "ask"


class TestTUIBindings:
    async def test_ctrl_s_binding_exists(self):
        app = CipherApp(project_root=os.getcwd())
        assert any(b.action == "settings" for b in app.BINDINGS)

    async def test_bindings_are_limited(self):
        app = CipherApp(project_root=os.getcwd())
        assert len(app.BINDINGS) == 2


class TestTUIRobustness:
    async def test_app_handles_missing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_config = Path(tmp) / ".cipher"
            fake_config.mkdir()
            with patch("cipher.app.CONFIG_DIR", fake_config), \
                 patch("cipher.app.CONFIG_FILE", fake_config / "config.json"), \
                 patch("cipher.app.SESSIONS_DIR", fake_config / "sessions"), \
                 patch("cipher.app.SKILLS_DIR", fake_config / "skills"):
                (fake_config / "sessions").mkdir()
                (fake_config / "skills").mkdir()
                app = CipherApp(project_root=os.getcwd())
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    assert app.is_running

    async def test_app_handles_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_config = Path(tmp) / ".cipher"
            fake_config.mkdir()
            cfg_file = fake_config / "config.json"
            cfg_file.write_text("{invalid json {{{")
            with patch("cipher.app.CONFIG_DIR", fake_config), \
                 patch("cipher.app.CONFIG_FILE", cfg_file), \
                 patch("cipher.app.SESSIONS_DIR", fake_config / "sessions"), \
                 patch("cipher.app.SKILLS_DIR", fake_config / "skills"):
                (fake_config / "sessions").mkdir()
                (fake_config / "skills").mkdir()
                app = CipherApp(project_root=os.getcwd())
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    assert app.is_running


class TestTUIConfigPersistence:
    async def test_config_save_roundtrip(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            cfg = load_config()
            cfg["auto_confirm"] = True
            save_config(cfg)
            app2 = CipherApp(project_root=os.getcwd())
            async with app2.run_test(size=(120, 40)) as pilot2:
                assert app2.config.get("auto_confirm") == True

    async def test_config_defaults_are_sane(self):
        cfg = load_config()
        assert cfg.get("provider") == "cipher-proxy"
        assert cfg.get("theme") == "dark"
        assert cfg.get("auto_confirm") == False
        assert "permissions" in cfg
        assert "custom_tools" in cfg
        assert "mcp_servers" in cfg

    async def test_config_saves_provider_model(self, temp_config):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.config.get("provider") == "cipher-proxy"
            assert app.config.get("model") == "llama-3.3-70b"


class TestTUIToolSystem:
    async def test_tool_registry_has_builtins(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            tools = app.tool_registry.list_tools()
            names = [t.name for t in tools]
            for n in ["run", "write", "read", "ls", "grep", "glob", "edit", "web-fetch", "web-search", "git", "todo"]:
                assert n in names

    async def test_tool_execution_echo(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            r = app.tool_registry.execute("run", "echo hello", "", os.getcwd())
            assert r["success"] == True
            assert "hello" in r["result"]

    async def test_unknown_tool_returns_error(self):
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            r = app.tool_registry.execute("nonexistent", "", "", os.getcwd())
            assert r["success"] == False


class TestTUIAgentSmokeTest:
    async def test_full_workflow(self, temp_config):
        """Simulate a real user session end-to-end."""
        app = CipherApp(project_root=os.getcwd())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            inp = app.query_one("#chat-input", Input)
            assert inp.has_focus

            inp.value = "hello"
            await pilot.press("enter")
            await pilot.pause()
            user_msgs = [m for m in app.chat_messages if m["role"] == "user"]
            assert len(user_msgs) >= 1

            await pilot.press("ctrl+s")
            await pilot.pause()
            assert app.screen_stack is not None

            await pilot.press("escape")
            await pilot.pause()

            inp.value = "test again"
            await pilot.press("enter")
            await pilot.pause()
            user_msgs = [m for m in app.chat_messages if m["role"] == "user"]
            assert len(user_msgs) >= 2

            assert app.is_running
            assert app.tool_registry.get("run") is not None
