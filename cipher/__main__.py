"""Cipher CLI entry point"""
import os
import sys
import json
from cipher.provider import AIProvider, PROVIDERS


def interactive_setup():
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal
    from textual.widgets import Static, Button, Input
    from textual.screen import Screen

    class ProviderSelectScreen(Screen):
        def compose(self) -> ComposeResult:
            with Container(id="setup-container"):
                yield Static("  CIPHER SETUP", id="setup-title")
                yield Static("Choose your AI provider", classes="setup-subtitle")
                yield Static("LOCAL - NO KEY NEEDED", classes="setup-section")
                for pid, info in PROVIDERS.items():
                    if info.get("type") == "local":
                        yield Button(f"{info['name']}  -  {info['desc']}", id=f"provider-{pid}", variant="default")
                yield Static("CLOUD - FREE TIER (NEEDS API KEY)", classes="setup-section")
                for pid, info in PROVIDERS.items():
                    if info.get("type") != "local":
                        yield Button(f"{info['name']}  -  {info['desc']}", id=f"provider-{pid}", variant="default")

        def on_button_pressed(self, event: Button.Pressed):
            btn_id = event.button.id
            if btn_id and btn_id.startswith("provider-"):
                self.app.on_provider_selected(btn_id.replace("provider-", ""))

    class ModelSelectScreen(Screen):
        BINDINGS = [("escape", "app.pop_screen", "Back")]
        def __init__(self, provider_id):
            super().__init__()
            self.provider_id = provider_id
        def compose(self) -> ComposeResult:
            info = PROVIDERS.get(self.provider_id, {})
            with Container(id="setup-container"):
                yield Static(f"  {info['name']}", id="setup-title")
                yield Static("Select a model", classes="setup-subtitle")
                for m in info.get("models", []):
                    tag = " [FREE]" if m.get("free") else ""
                    yield Button(f"{m['name']}{tag}", id=f"model-{m['id']}", variant="default")

        def on_button_pressed(self, event: Button.Pressed):
            btn_id = event.button.id
            if btn_id and btn_id.startswith("model-"):
                self.app.on_model_selected(self.provider_id, btn_id.replace("model-", "", 1))

    class ApiKeyScreen(Screen):
        BINDINGS = [("escape", "app.pop_screen", "Back")]
        def __init__(self, provider_id, model_id):
            super().__init__()
            self.provider_id = provider_id
            self.model_id = model_id
        def compose(self) -> ComposeResult:
            info = PROVIDERS.get(self.provider_id, {})
            env_key = info.get("env_key", "API_KEY")
            with Container(id="setup-container"):
                yield Static(f"  {info['name']} API KEY", id="setup-title")
                yield Static(f"Enter your {env_key}", classes="setup-subtitle")
                yield Static(f"Get one at: {info.get('signup_url', 'provider website')}", classes="setup-hint")
                yield Input(placeholder=env_key, id="api-key-input", password=True)
                with Horizontal():
                    yield Button("Save & Continue", id="api-key-save", variant="primary")
                    yield Button("Skip", id="api-key-skip", variant="default")

        def on_button_pressed(self, event: Button.Pressed):
            if event.button.id == "api-key-save":
                key = self.query_one("#api-key-input", Input).value.strip()
                if key:
                    self.app.on_api_key_entered(self.provider_id, self.model_id, key)
                    return
            self.app.on_api_key_entered(self.provider_id, self.model_id, None)

    class SetupApp(App):
        DEFAULT_CSS = """
        Screen { background: #050505; }
        #setup-container { width: 70; height: auto; margin: 1 1; background: #0a0a0a; border: tall #f5c542; padding: 1 3; }
        #setup-title { color: #f5c542; text-align: center; text-style: bold; margin-bottom: 1; }
        .setup-subtitle { text-align: center; color: #888; margin-bottom: 1; }
        .setup-hint { text-align: center; color: #555; margin-bottom: 1; }
        .setup-section { color: #444; margin-top: 1; margin-bottom: 0; }
        Button { width: 100%; margin: 0 0 0 0; }
        #api-key-input { margin: 1 0; }
        """
        def __init__(self):
            super().__init__()
            self.result = {"provider": "ollama", "model": "ollama/qwen3:14b", "api_key": ""}

        def on_mount(self):
            self.push_screen(ProviderSelectScreen())

        def on_provider_selected(self, provider_id):
            self.result["provider"] = provider_id
            info = PROVIDERS.get(provider_id, {})
            models = info.get("models", [])

            if info.get("type") == "local":
                if not models:
                    self.exit(self.result)
                    return
                if len(models) == 1:
                    self.on_api_key_entered(provider_id, models[0]["id"], None)
                else:
                    self.push_screen(ModelSelectScreen(provider_id))
            else:
                if not models:
                    self.exit(self.result)
                    return
                if len(models) == 1:
                    self.push_screen(ApiKeyScreen(provider_id, models[0]["id"]))
                else:
                    self.push_screen(ModelSelectScreen(provider_id))

        def on_model_selected(self, provider_id, model_id):
            self.result["model"] = model_id
            info = PROVIDERS.get(provider_id, {})
            if info.get("type") == "local":
                existing = os.getenv(info.get("env_key", ""), "") if info.get("env_key") else ""
                if existing:
                    self.result["api_key"] = existing
                self.exit(self.result)
            else:
                self.push_screen(ApiKeyScreen(provider_id, model_id))

        def on_api_key_entered(self, provider_id, model_id, api_key):
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
    config_dir = os.path.expanduser("~/.cipher")
    os.makedirs(config_dir, exist_ok=True)
    cfg = {
        "provider": result.get("provider", "ollama"),
        "model": result.get("model", "ollama/qwen3:14b"),
    }
    if result.get("api_key"):
        cfg["api_key"] = result["api_key"]
    with open(os.path.join(config_dir, "config.json"), "w") as f:
        json.dump(cfg, f, indent=2)


def main():
    project_root = os.getcwd()

    config_dir = os.path.expanduser("~/.cipher")
    config_path = os.path.join(config_dir, "config.json")
    saved_provider = ""
    saved_model = ""
    saved_api_key = None
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            saved_provider = cfg.get("provider", "")
            saved_model = cfg.get("model", "")
            saved_api_key = cfg.get("api_key")
        except Exception:
            pass

    provider = os.getenv("CIPHER_PROVIDER", saved_provider)
    model = os.getenv("CIPHER_MODEL", saved_model)
    api_key = os.getenv("OPENAI_API_KEY", saved_api_key or "")

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
            result = interactive_setup()
            if result:
                provider = result["provider"]
                model = result["model"]
                api_key = result.get("api_key") or api_key
                save_user_config(result)
            from cipher.app import run_tui
            run_tui(project_root=project_root, provider=provider, model=model, api_key=api_key)
            return
        elif args[i] in ("--version", "-v"):
            print("cip v0.3.0")
            return
        elif args[i] in ("--help", "-h"):
            print("Usage: cip [--setup] [--provider PROVIDER] [--model MODEL] [--api-key KEY] [--dir PATH]")
            print("\nOptions:")
            print("  --setup              Interactive provider selection")
            print("  --provider PROVIDER  AI provider (ollama, deepseek, etc.)")
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

    if not provider:
        result = interactive_setup()
        if result:
            provider = result["provider"]
            model = result["model"]
            api_key = result.get("api_key") or api_key
            save_user_config(result)

    if not os.path.isdir(project_root):
        print(f"Error: not a directory: {project_root}")
        sys.exit(1)

    from cipher.app import run_tui
    run_tui(project_root=project_root, provider=provider, model=model, api_key=api_key)


if __name__ == "__main__":
    main()
