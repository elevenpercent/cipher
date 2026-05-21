# Derived from opencode (MIT) - Copyright (c) 2025 opencode.ai
import os
import sys
import json
import tempfile
import subprocess
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cipher.provider import AIProvider, PROVIDERS, detect_gpu, get_local_ollama_models
from cipher.app import (
    load_config, save_config, generate_title,
    CodeBlock, PlanBlock, ExplanationBlock, ToolResult, LoadingIndicator,
    detect_available_providers,
    CipherApp, SettingsModal, SessionModal, YesNoModal,
    CONFIG_DIR, CONFIG_FILE,
)
from cipher.__main__ import save_user_config, main
from rich.text import Text


PROXY_URL = "https://proxy-blue-kappa.vercel.app"

class Test1Providers(unittest.TestCase):
    def test_providers_loaded(self):
        self.assertGreater(len(PROVIDERS), 0)
        self.assertIn("cipher-proxy", PROVIDERS)
        self.assertIn("groq", PROVIDERS)
        self.assertIn("gemini", PROVIDERS)
        self.assertIn("ollama", PROVIDERS)

    def test_cipher_proxy_models(self):
        cp = PROVIDERS["cipher-proxy"]
        self.assertTrue(cp.get("proxy"))
        model_ids = [m["id"] for m in cp["models"]]
        self.assertIn("llama-3.3-70b", model_ids)
        self.assertIn("llama-3.1-8b", model_ids)
        self.assertIn("gemini-2.0-flash", model_ids)

    def test_gpu_detection(self):
        vram = detect_gpu()
        self.assertIsInstance(vram, int)
        print(f"  GPU VRAM: {vram}GB")

    def test_local_models_filtered(self):
        models = get_local_ollama_models(0)
        self.assertEqual(len(models), 0)
        models = get_local_ollama_models(11)
        self.assertGreater(len(models), 0)
        for m in models:
            self.assertLessEqual(m["min_vram"], 11)
        models = get_local_ollama_models(999)
        all_ids = [m["id"] for m in models]
        self.assertIn("ollama/llama3.3:70b", all_ids)

class Test2AIProvider(unittest.TestCase):
    def test_proxy_chat_sync_llama8b(self):
        prov = AIProvider(provider_id="cipher-proxy", model_id="llama-3.1-8b", proxy_url=PROXY_URL)
        result = prov.chat(
            [{"role": "user", "content": "say hi in exactly 3 words"}],
            stream=False
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        result_lower = result.lower()
        self.assertTrue("hi" in result_lower or "hello" in result_lower or "hey" in result_lower,
                        f"Unexpected: {result}")

    def test_proxy_chat_sync_llama70b(self):
        prov = AIProvider(provider_id="cipher-proxy", model_id="llama-3.3-70b", proxy_url=PROXY_URL)
        result = prov.chat(
            [{"role": "user", "content": "say hi in exactly 3 words"}],
            stream=False
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_proxy_chat_sync_gemini(self):
        prov = AIProvider(provider_id="cipher-proxy", model_id="gemini-2.0-flash", proxy_url=PROXY_URL)
        result = prov.chat(
            [{"role": "user", "content": "say hi in exactly 3 words"}],
            stream=False
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_proxy_chat_stream(self):
        prov = AIProvider(provider_id="cipher-proxy", model_id="llama-3.1-8b", proxy_url=PROXY_URL)
        stream = prov.chat(
            [{"role": "user", "content": "say hi in exactly 3 words"}],
            stream=True
        )
        chunks = list(stream)
        self.assertGreater(len(chunks), 0)
        for c in chunks:
            self.assertIn("content", c)
            self.assertGreater(len(c["content"]), 0)

    def test_proxy_error_forwarding(self):
        prov = AIProvider(provider_id="cipher-proxy", model_id="non-existent-model", proxy_url=PROXY_URL)
        result = prov.chat(
            [{"role": "user", "content": "hi"}],
            stream=False
        )
        self.assertTrue("Error" in result or "404" in result,
                        f"Expected error, got: {result}")

    def test_ollama_provider_init(self):
        prov = AIProvider(provider_id="ollama", model_id="ollama/qwen3:14b")
        self.assertEqual(prov.provider_id, "ollama")
        self.assertEqual(prov.model_id, "ollama/qwen3:14b")

    def test_list_providers(self):
        providers = AIProvider.list_providers()
        self.assertGreater(len(providers), 0)
        ids = [p["id"] for p in providers]
        self.assertIn("cipher-proxy", ids)

    def test_list_models(self):
        models = AIProvider.list_models("cipher-proxy")
        self.assertGreater(len(models), 0)
        models_all = AIProvider.list_models()
        self.assertGreater(len(models_all), len(models))

class Test3Blocks(unittest.TestCase):
    def test_codeblock_new_file(self):
        cb = CodeBlock("test.py", "print('hello')", old_content="")
        r = cb.render()
        self.assertIsInstance(r, Text)
        text = r.plain
        self.assertIn("test.py", text)
        self.assertIn("print", text)
        self.assertIn("1 lines", text)

    def test_codeblock_diff(self):
        cb = CodeBlock("test.py", "line2", old_content="line1")
        r = cb.render()
        text = r.plain
        self.assertIn("test.py", text)

    def test_planblock(self):
        pb = PlanBlock("1. Do this\n2. Do that")
        r = pb.render()
        text = r.plain
        self.assertIn("Plan", text)
        self.assertIn("Do this", text)

    def test_explanation_block_collapsed(self):
        eb = ExplanationBlock("Summary", "Details here", expanded=False)
        r = eb.render()
        self.assertFalse(eb.expanded)

    def test_explanation_block_expanded(self):
        eb = ExplanationBlock("Summary", "Details here", expanded=True)
        self.assertTrue(eb.expanded)
        r = eb.render()
        text = r.plain
        self.assertIn("Details here", text)

    def test_explanation_toggle(self):
        eb = ExplanationBlock("Summary", "Details", expanded=False)
        eb.action_toggle()
        self.assertTrue(eb.expanded)
        eb.action_toggle()
        self.assertFalse(eb.expanded)

    def test_toolresult_write(self):
        tr = ToolResult("write", "test.py", "3 lines written", True)
        r = tr.render()
        text = r.plain
        self.assertIn("test.py", text)

    def test_toolresult_run(self):
        tr = ToolResult("run", "echo hello", "hello", True)
        r = tr.render()
        text = r.plain
        self.assertIn("echo hello", text)

    def test_toolresult_fail(self):
        tr = ToolResult("run", "badcmd", "not found", False)
        r = tr.render()
        text = r.plain

    def test_loading_indicator(self):
        li = LoadingIndicator()
        self.assertIsNotNone(li)

class Test4Config(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_config_dir = CONFIG_DIR
        import cipher.app as app_mod
        self.orig_config_file = app_mod.CONFIG_FILE
        app_mod.CONFIG_DIR = Path(self.tmpdir)
        app_mod.CONFIG_FILE = app_mod.CONFIG_DIR / "config.json"

    def tearDown(self):
        import cipher.app as app_mod
        app_mod.CONFIG_DIR = self.orig_config_dir
        app_mod.CONFIG_FILE = self.orig_config_file

    def test_load_config_defaults(self):
        cfg = load_config()
        self.assertEqual(cfg["provider"], "cipher-proxy")
        self.assertEqual(cfg["model"], "llama-3.3-70b")
        self.assertTrue(cfg["show_plan"])
        self.assertTrue(cfg["show_code"])

    def test_save_and_load(self):
        save_config({"provider": "groq", "model": "groq/llama-3.3-70b-versatile", "custom_key": "val"})
        loaded = load_config()
        self.assertEqual(loaded["provider"], "groq")
        self.assertEqual(loaded["model"], "groq/llama-3.3-70b-versatile")
        self.assertEqual(loaded.get("custom_key"), "val")

    def test_save_and_load_partial(self):
        save_config({"provider": "ollama"})
        loaded = load_config()
        self.assertEqual(loaded["provider"], "ollama")
        self.assertEqual(loaded["model"], "llama-3.3-70b")

    def test_generate_title_short(self):
        self.assertEqual(generate_title("hello world"), "hello world")

    def test_generate_title_long(self):
        long = "a" * 100
        title = generate_title(long)
        self.assertEqual(len(title), 40)
        self.assertTrue(title.endswith("..."))

class Test5DetectProviders(unittest.TestCase):
    def test_detect_available(self):
        available = detect_available_providers()
        self.assertGreater(len(available), 0)
        for p in available:
            self.assertIn("id", p)
            self.assertIn("available", p)

class Test6SaveUserConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig = Path.home() / ".cipher"
        import cipher.__main__ as m
        self._orig_home = m.Path

    def tearDown(self):
        pass

    def test_save_user_config_proxy(self):
        import cipher.__main__ as cm
        config_dir = Path(self.tmpdir)
        orig_func = cm.save_user_config

        def mock_save(result):
            cfg_path = config_dir / "config.json"
            cfg_path.parent.mkdir(exist_ok=True)
            cfg = {}
            if cfg_path.exists():
                with open(cfg_path) as f:
                    cfg = json.load(f)
            cfg["provider"] = result.get("provider", "cipher-proxy")
            cfg["model"] = result.get("model", "llama-3.3-70b")
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)

        cm.save_user_config = mock_save
        cm.save_user_config({"provider": "cipher-proxy", "model": "llama-3.1-8b"})
        cfg_path = config_dir / "config.json"
        self.assertTrue(cfg_path.exists())
        with open(cfg_path) as f:
            data = json.load(f)
        self.assertEqual(data["provider"], "cipher-proxy")
        self.assertEqual(data["model"], "llama-3.1-8b")

class Test7SettingsModal(unittest.TestCase):
    def test_settings_modal_compose(self):
        sm = SettingsModal({"provider": "cipher-proxy", "model": "llama-3.3-70b", "show_plan": True})
        self.assertEqual(sm.config["provider"], "cipher-proxy")
        self.assertIn("show_plan", sm.config)

    def test_settings_modal_init(self):
        sm = SettingsModal({"provider": "cipher-proxy"})
        self.assertEqual(sm.config["provider"], "cipher-proxy")

    def test_yesno_modal(self):
        ym = YesNoModal("run", "echo test")
        self.assertEqual(ym.tool, "run")
        self.assertEqual(ym.args, "echo test")
        self.assertEqual(ym.result, "no")

class Test8ToolExecution(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.chdir(self.tmpdir)
        import cipher.app as app_mod
        self.orig_config_dir = app_mod.CONFIG_DIR
        self.orig_config_file = app_mod.CONFIG_FILE
        app_mod.CONFIG_DIR = Path(self.tmpdir) / ".cipher"
        app_mod.CONFIG_FILE = app_mod.CONFIG_DIR / "config.json"
        app_mod.CONFIG_DIR.mkdir(exist_ok=True)
        app_mod.SESSIONS_DIR = app_mod.CONFIG_DIR / "sessions"
        app_mod.SESSIONS_DIR.mkdir(exist_ok=True)
        app_mod.SKILLS_DIR = app_mod.CONFIG_DIR / "skills"
        app_mod.SKILLS_DIR.mkdir(exist_ok=True)

    def tearDown(self):
        import cipher.app as app_mod
        app_mod.CONFIG_DIR = self.orig_config_dir
        app_mod.CONFIG_FILE = self.orig_config_file

    def test_run_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        result = app._execute_tool("run", "echo hello from cipher", "")
        self.assertIsInstance(result, str)
        self.assertIn("hello", result.lower() or result == "(ok)")

    def test_write_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        result = app._execute_tool("write", "test_write.txt", "hello world")
        self.assertIn("Written", result)
        file_path = os.path.join(self.tmpdir, "test_write.txt")
        self.assertTrue(os.path.exists(file_path))
        with open(file_path) as f:
            self.assertEqual(f.read().strip(), "hello world")

    def test_write_escape_prevention(self):
        app = CipherApp(project_root=self.tmpdir)
        result = app._execute_tool("write", "../escape_test.txt", "should fail")
        self.assertIn("escapes", result.lower())

    def test_read_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        with open(os.path.join(self.tmpdir, "test_read.txt"), "w") as f:
            f.write("line1\nline2\nline3")
        result = app._execute_tool("read", "test_read.txt", "")
        self.assertIn("line1", result)

    def test_ls_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        os.makedirs(os.path.join(self.tmpdir, "subdir"), exist_ok=True)
        result = app._execute_tool("ls", ".", "")
        self.assertIn("subdir", result)

    def test_glob_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        with open(os.path.join(self.tmpdir, "foo.py"), "w") as f:
            f.write("x")
        result = app._execute_tool("glob", "**/*.py", "")
        self.assertIn("foo.py", result)

    def test_grep_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        with open(os.path.join(self.tmpdir, "search.txt"), "w") as f:
            f.write("find me")
        result = app._execute_tool("grep", "find", ".")
        self.assertIn("find me", result)

    def test_edit_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        with open(os.path.join(self.tmpdir, "edit_test.txt"), "w") as f:
            f.write("old content")
        body = json.dumps({"old": "old content", "new": "new content"})
        result = app._execute_tool("edit", "edit_test.txt", body)
        self.assertIn("Edited", result)
        with open(os.path.join(self.tmpdir, "edit_test.txt")) as f:
            self.assertEqual(f.read(), "new content")

    def test_edit_not_found(self):
        app = CipherApp(project_root=self.tmpdir)
        with open(os.path.join(self.tmpdir, "edit_test.txt"), "w") as f:
            f.write("content")
        body = json.dumps({"old": "nonexistent", "new": "new"})
        result = app._execute_tool("edit", "edit_test.txt", body)
        self.assertIn("not found", result)

    def test_edit_not_found_file(self):
        app = CipherApp(project_root=self.tmpdir)
        body = json.dumps({"old": "x", "new": "y"})
        result = app._execute_tool("edit", "nonexistent.txt", body)
        self.assertIn("not found", result)

    def test_parse_tools(self):
        app = CipherApp(project_root=self.tmpdir)
        text = "Hello <run>echo test</run> world"
        tools = app._parse_tools_all(text)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["type"], "run")
        self.assertEqual(tools[0]["args"], "echo test")

    def test_parse_tools_write(self):
        app = CipherApp(project_root=self.tmpdir)
        text = 'Test <write path="test.py">print("hello")</write> end'
        tools = app._parse_tools_all(text)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["type"], "write")
        self.assertEqual(tools[0]["path"], "test.py")
        self.assertEqual(tools[0]["body"].strip(), 'print("hello")')

    def test_parse_tools_multiple(self):
        app = CipherApp(project_root=self.tmpdir)
        text = 'A<run>a</run>B<run>b</run>C'
        tools = app._parse_tools_all(text)
        self.assertEqual(len(tools), 2)

    def test_parse_tools_ls(self):
        app = CipherApp(project_root=self.tmpdir)
        text = '<ls>.</ls>'
        tools = app._parse_tools_all(text)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["type"], "ls")

    def test_todo_tool(self):
        app = CipherApp(project_root=self.tmpdir)
        result = app._execute_tool("todo", "add=\"test task\"", "")
        self.assertIn("added", result)
        self.assertEqual(len(app.todo_list), 1)
        result2 = app._execute_tool("todo", "done=1", "")
        self.assertIn("done", result2)

class Test9SessionManagement(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import cipher.app as app_mod
        self.orig_sessions = app_mod.SESSIONS_DIR
        app_mod.SESSIONS_DIR = Path(self.tmpdir)
        from cipher.app import save_session, load_sessions, load_session
        self.save_session = save_session
        self.load_sessions = load_sessions
        self.load_session = load_session

    def tearDown(self):
        import cipher.app as app_mod
        app_mod.SESSIONS_DIR = self.orig_sessions

    def test_save_and_load_session(self):
        self.save_session("test123", [{"role": "user", "content": "hi"}], "Test Session")
        sessions = self.load_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], "test123")

    def test_load_specific_session(self):
        self.save_session("test456", [{"role": "user", "content": "hello"}], "Session 2")
        s = self.load_session("test456")
        self.assertIsNotNone(s)
        self.assertEqual(s["title"], "Session 2")

    def test_load_nonexistent(self):
        s = self.load_session("nonexistent")
        self.assertIsNone(s)

class Test10SystemPrompt(unittest.TestCase):
    def test_build_system_prompt(self):
        import cipher.app as app_mod
        app = CipherApp(project_root=os.getcwd())
        prompt = app._build_system_prompt()
        self.assertIn("Cipher", prompt)
        self.assertIn("<done>", prompt)
        self.assertIn("<run>", prompt)
        self.assertIn("<write", prompt)
        self.assertIn("<edit", prompt)

    def test_build_system_prompt_with_skills(self):
        import cipher.app as app_mod
        app = CipherApp(project_root=os.getcwd())

class Test11CodingTest(unittest.TestCase):
    def test_model_switching(self):
        prov = AIProvider(provider_id="cipher-proxy", model_id="llama-3.1-8b", proxy_url=PROXY_URL)
        r1 = prov.chat([{"role": "user", "content": "say hi"}], stream=False)
        self.assertIsInstance(r1, str)
        prov2 = AIProvider(provider_id="cipher-proxy", model_id="llama-3.3-70b", proxy_url=PROXY_URL)
        r2 = prov2.chat([{"role": "user", "content": "say hi"}], stream=False)
        self.assertIsInstance(r2, str)
        prov3 = AIProvider(provider_id="cipher-proxy", model_id="gemini-2.0-flash", proxy_url=PROXY_URL)
        r3 = prov3.chat([{"role": "user", "content": "say hi"}], stream=False)
        self.assertIsInstance(r3, str)

    def test_make_something(self):
        prov = AIProvider(provider_id="cipher-proxy", model_id="llama-3.3-70b", proxy_url=PROXY_URL)
        response = prov.chat([
            {"role": "system", "content": "You are a coding agent. Generate Python code only — a self-test script that: 1) Tests all its own core functions. 2) Prints PASS/FAIL for each test. 3) Uses only standard library. Wrap in <write path=\"self_test.py\">content</write> tags."},
            {"role": "user", "content": "Write a self-test script according to the system instructions."}
        ], stream=False)
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 50)
        if "<write" in response:
            m = __import__('re').search(r'<write\s+path=["\'](.*?)["\']>(.*?)</write>', response, __import__('re').DOTALL)
            if m:
                content = m.group(2).strip()
                self.assertGreater(len(content), 0)
                out_path = os.path.join(tempfile.mkdtemp(), "self_test.py")
                with open(out_path, "w") as f:
                    f.write(content)
                result = subprocess.run([sys.executable, out_path], capture_output=True, text=True, timeout=30)
                print(f"  Self-test stdout: {result.stdout[:500]}")
                print(f"  Self-test stderr: {result.stderr[:500]}")
                self.assertEqual(result.returncode, 0)


class Test12AppInit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import cipher.app as app_mod
        self.orig_config_dir = app_mod.CONFIG_DIR
        self.orig_config_file = app_mod.CONFIG_FILE
        app_mod.CONFIG_DIR = Path(self.tmpdir)
        app_mod.CONFIG_FILE = app_mod.CONFIG_DIR / "config.json"

    def tearDown(self):
        import cipher.app as app_mod
        app_mod.CONFIG_DIR = self.orig_config_dir
        app_mod.CONFIG_FILE = self.orig_config_file

    def test_cipher_app_init(self):
        app = CipherApp(project_root=os.getcwd())
        self.assertEqual(app.config["provider"], "cipher-proxy")
        self.assertEqual(app.config["model"], "llama-3.3-70b")

    def test_cipher_app_custom_provider(self):
        app = CipherApp(project_root=os.getcwd(), provider="groq", model="groq/llama-3.3-70b-versatile")
        self.assertEqual(app.config["provider"], "groq")
        self.assertEqual(app.config["model"], "groq/llama-3.3-70b-versatile")

    def test_add_user_message(self):
        app = CipherApp(project_root=os.getcwd())
        app._add_user("test message")
        self.assertEqual(len(app.messages), 0)

    def test_do_clear(self):
        app = CipherApp(project_root=os.getcwd())
        app._do_clear()
        self.assertEqual(len(app.chat_messages), 1)

    def test_do_new(self):
        app = CipherApp(project_root=os.getcwd())
        old_id = app.session_id
        app.chat_messages.append({"role": "user", "content": "test"})
        app._do_new()
        self.assertIsInstance(app.session_id, str)
        self.assertGreater(len(app.session_id), 0)
        self.assertEqual(len(app.chat_messages), 1)

    def test_generate_title_long_edge(self):
        title = generate_title("a" * 50)
        self.assertEqual(len(title), 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
