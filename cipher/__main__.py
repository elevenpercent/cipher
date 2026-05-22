import os
import sys
import json
import subprocess
import webbrowser
from pathlib import Path
from cipher.provider import AIProvider, PROVIDERS, detect_gpu, get_local_ollama_models


def install_ollama():
    """Try to auto-install Ollama on Windows."""
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal
    from textual.widgets import Static, Button, Input
    from textual.screen import Screen

    class InstallPrompt(Screen):
        def compose(self) -> ComposeResult:
            with Container(id="install-panel"):
                yield Static("  OLLAMA NOT FOUND", id="install-title")
                yield Static("", id="install-spacer")
                yield Static("  Local AI models require Ollama to be installed.", classes="install-text")
                yield Static("  Cipher can open the Ollama download page for you.", classes="install-text")
                yield Static("", id="install-spacer")
                yield Static("  After installing, restart Cipher.", classes="install-hint")
                with Horizontal(id="install-buttons"):
                    yield Button("  OPEN DOWNLOAD PAGE  ", id="install-open", variant="primary")
                    yield Button("  SKIP  ", id="install-skip", variant="default")

        def on_button_pressed(self, event: Button.Pressed):
            if event.button.id == "install-open":
                webbrowser.open("https://ollama.com/download")
            self.dismiss(True)

    class InstallApp(App):
        CSS = """
        Screen { background: #050505; }
        .install-text { text-align: center; color: #ccc; }
        .install-hint { text-align: center; color: #666; margin-top: 1; }
        """
        def __init__(self):
            super().__init__()

    app = InstallApp()
    app.run()


def interactive_setup():
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, VerticalScroll
    from textual.widgets import Static, Button, Input, Label
    from textual.screen import Screen

    gpu_vram = detect_gpu()
    ollama_models = get_local_ollama_models(gpu_vram)
    local_available = len(ollama_models) > 0

    class ProviderSelectScreen(Screen):
        def __init__(self):
            super().__init__()
            self.model_map = {}
            self.provider_map = {}

        def compose(self) -> ComposeResult:
            with Container(id="setup-outer"):
                yield Static("  CIPHER  //  SETUP", id="setup-title")
                yield Static("  Pick a provider to get started. Scroll down for more options.", classes="setup-subtitle")
                with VerticalScroll(id="setup-scroll"):
                    with Container(id="setup-container"):
                        yield Static("FREE — NO KEY NEEDED", classes="setup-section")
                        yield Button("  ★  Cipher Proxy  —  Llama 3.3 70B + Gemini (free, instant)", id="provider-cipher-proxy", variant="primary")
                        yield Static("", classes="setup-spacer")
                        if local_available:
                            yield Static("LOCAL MODELS (Ollama)", classes="setup-section")
                            for m in ollama_models:
                                safe = m['id'].replace('/', '_').replace(':', '_').replace('.', '_')
                                self.model_map[f"model-{safe}"] = m['id']
                                yield Button(f"  {m['name']}", id=f"model-{safe}", variant="default")
                            yield Static("", classes="setup-spacer")
                        yield Static("BRING YOUR OWN KEY", classes="setup-section")
                        for pid, info in PROVIDERS.items():
                            if info.get("env_key") and not info.get("proxy"):
                                safe_pid = pid.replace('/', '_').replace(':', '_').replace('.', '_')
                                self.provider_map[f"provider-{safe_pid}"] = pid
                                yield Button(f"  {info['name']}  —  {info['desc']}", id=f"provider-{safe_pid}", variant="default")

        def on_button_pressed(self, event: Button.Pressed):
            btn_id = event.button.id
            if btn_id and btn_id.startswith("model-"):
                model_id = self.model_map.get(btn_id, "")
                if model_id:
                    self.app.on_selection("ollama", model_id, None)
            elif btn_id and btn_id.startswith("provider-"):
                pid = self.provider_map.get(btn_id, btn_id.replace("provider-", ""))
                info = PROVIDERS.get(pid, {})
                models = info.get("models", [])
                if len(models) == 1:
                    self.app.on_selection(pid, models[0]["id"], None)
                else:
                    self.app.on_no_models(pid)

    class ApiKeyScreen(Screen):
        BINDINGS = [("escape", "app.pop_screen", "Back")]
        def __init__(self, provider_id):
            super().__init__()
            self.provider_id = provider_id
        def compose(self) -> ComposeResult:
            info = PROVIDERS.get(self.provider_id, {})
            env_key = info.get("env_key", "API_KEY")
            with Container(id="setup-container"):
                yield Static(f"  {info['name']}", id="setup-title")
                yield Static(f"  Enter your {env_key}", classes="setup-subtitle")
                yield Static(f"  Get one: {info.get('signup_url', 'provider website')}", classes="setup-hint")
                yield Input(placeholder=env_key, id="api-key-input", password=True)
                with Horizontal():
                    yield Button("Save", id="api-key-save", variant="primary")
                    yield Button("Skip", id="api-key-skip", variant="default")

        def on_button_pressed(self, event: Button.Pressed):
            info = PROVIDERS.get(self.provider_id, {})
            models = info.get("models", [])
            mid = models[0]["id"] if models else ""
            if event.button.id == "api-key-save":
                key = self.query_one("#api-key-input", Input).value.strip()
                self.app.on_selection(self.provider_id, mid, key or None)
            else:
                self.app.on_selection(self.provider_id, mid, None)

    class SetupApp(App):
        CSS = """
        Screen { background: #050505; }
        #setup-outer { height: 100%; padding: 1 2; }
        #setup-title { color: #fab283; text-style: bold; margin-bottom: 1; }
        #setup-scroll { height: 1fr; }
        #setup-container { padding: 0; }
        .setup-subtitle { color: #888888; margin-bottom: 1; }
        .setup-spacer { height: 1; }
        .setup-section { color: #fab283; text-style: bold; margin-top: 1; margin-bottom: 0; }
        .setup-hint { color: #555; margin-bottom: 1; }
        .setup-unavail { color: #444; }
        Button { width: 100%; margin: 0 0 0 0; }
        Button.primary { background: #fab283 20%; border: tall #fab283; }
        """
        def __init__(self):
            super().__init__()
            self.result = {"provider": "cipher-proxy", "model": "llama-3.3-70b", "api_key": ""}

        def on_mount(self):
            self.push_screen(ProviderSelectScreen())

        def on_no_models(self, provider_id):
            info = PROVIDERS.get(provider_id, {})
            models = info.get("models", [])
            mid = models[0]["id"] if models else ""
            self.on_selection(provider_id, mid, None)

        def on_selection(self, provider_id, model_id, api_key):
            self.result["provider"] = provider_id
            self.result["model"] = model_id
            if api_key:
                self.result["api_key"] = api_key
                env_key = PROVIDERS.get(provider_id, {}).get("env_key")
                if env_key:
                    os.environ[env_key] = api_key
            self.exit(self.result)

    app = SetupApp()
    result = app.run()
    return result


def save_user_config(result):
    config_dir = Path.home() / ".cipher"
    config_dir.mkdir(exist_ok=True)
    cfg_path = config_dir / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except Exception:
            pass
    cfg["provider"] = result.get("provider", "cipher-proxy")
    cfg["model"] = result.get("model", "llama-3.3-70b")
    if result.get("proxy_url"):
        cfg["proxy_url"] = result["proxy_url"]
    if result.get("api_key"):
        cfg["api_key"] = result["api_key"]
    if cfg.get("provider") and PROVIDERS.get(cfg["provider"], {}).get("proxy"):
        cfg["proxy_url"] = cfg.get("proxy_url", "https://proxy-blue-kappa.vercel.app")
        cfg.pop("api_key", None)
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)


def main():
    project_root = os.getcwd()

    config_dir = Path.home() / ".cipher"
    config_path = config_dir / "config.json"
    saved_provider = ""
    saved_model = ""
    saved_api_key = None
    saved_proxy_url = "https://proxy-blue-kappa.vercel.app"
    first_run = False
    if config_path.exists():
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            saved_provider = cfg.get("provider", "")
            saved_model = cfg.get("model", "")
            saved_api_key = cfg.get("api_key")
            saved_proxy_url = cfg.get("proxy_url", saved_proxy_url)
        except Exception:
            pass
    else:
        first_run = True

    provider = os.getenv("CIPHER_PROVIDER", saved_provider) or "cipher-proxy"
    model = os.getenv("CIPHER_MODEL", saved_model) or "llama-3.3-70b"
    provider_config = PROVIDERS.get(provider, {})
    if provider_config.get("proxy"):
        api_key = ""
    else:
        env_key = provider_config.get("env_key", "")
        api_key = os.getenv(env_key, "") if env_key else ""
        if not api_key and saved_api_key:
            api_key = saved_api_key

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]; i += 2
        elif args[i] == "--provider" and i + 1 < len(args):
            provider = args[i + 1].lower(); i += 2
        elif args[i] == "--api-key" and i + 1 < len(args):
            api_key = args[i + 1]; i += 2
        elif args[i] == "--dir" and i + 1 < len(args):
            project_root = os.path.abspath(args[i + 1]); i += 2
        elif args[i] == "--setup":
            first_run = True; i += 1
        elif args[i] in ("--version", "-v"):
            print("cip v0.6.0")
            return
        elif args[i] in ("--help", "-h"):
            print("Usage: cip [--setup] [--provider PROVIDER] [--model MODEL] [--api-key KEY] [--dir PATH]")
            print("\nOptions:")
            print("  --setup              Interactive provider selection")
            print("  --provider PROVIDER  AI provider (ollama, groq, etc.)")
            print("  --model MODEL        Model name")
            print("  --api-key KEY        API key")
            print("  --dir PATH           Working directory")
            print("  --help, -h           Show this help")
            print("\nProviders:")
            for pid, info in PROVIDERS.items():
                if info.get("type") == "local":
                    tag = " (local, no key)"
                elif info.get("type") == "cloud-free":
                    tag = f" (free tier: {info.get('free_tokens', 'free tier available')})"
                else:
                    tag = " (needs API key)"
                print(f"  {pid}{tag}  {info['name']} - {info['desc']}")
            print("\nModels:")
            for pid, info in PROVIDERS.items():
                print(f"\n  {info['name']}:")
                for m in info.get("models", []):
                    free = "FREE" if m.get("free") else ""
                    print(f"    {m['name']:<35} {free}")
            return
        else:
            i += 1

    if first_run:
        result = interactive_setup()
        if result:
            provider = result["provider"]
            model = result["model"]
            api_key = result.get("api_key") or api_key
            save_user_config(result)

            if provider == "ollama":
                try:
                    subprocess.run(["ollama", "list"], capture_output=True, timeout=3)
                except Exception:
                    install_ollama()

    if not os.path.isdir(project_root):
        print(f"Error: not a directory: {project_root}")
        sys.exit(1)

    from cipher.app import run_tui
    run_tui(project_root=project_root, provider=provider, model=model, api_key=api_key, proxy_url=saved_proxy_url)


if __name__ == "__main__":
    main()
