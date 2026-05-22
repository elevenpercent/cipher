import os
import sys
import importlib
import inspect
import traceback
from pathlib import Path

PLUGINS_DIR = Path.home() / ".cipher" / "plugins"


class Plugin:
    name = ""
    version = "1.0.0"
    description = ""

    def on_load(self, app):
        pass

    def on_unload(self, app):
        pass

    def on_tool_execute(self, tool, args, body):
        return None

    def on_tool_result(self, tool, args, result):
        return None

    def on_chat_message(self, messages):
        return None

    def on_settings_open(self, config):
        return config

    def on_settings_save(self, config):
        return config

    def on_app_start(self, app):
        pass

    def on_app_exit(self, app):
        pass

    def on_stream_chunk(self, chunk):
        return None

    def on_provider_change(self, provider_id, model_id):
        pass


class PluginManager:
    def __init__(self):
        self.plugins = []
        self._hook_registry = {}

    def discover(self):
        PLUGINS_DIR.mkdir(exist_ok=True)
        init_file = PLUGINS_DIR / "__init__.py"
        if not init_file.exists():
            init_file.write_text("")
        sys.path.insert(0, str(PLUGINS_DIR.parent))
        loaded = 0
        for f in sorted(PLUGINS_DIR.glob("*.py")):
            if f.name == "__init__.py":
                continue
            try:
                mod_name = f"plugins.{f.stem}"
                if mod_name in sys.modules:
                    mod = importlib.reload(sys.modules[mod_name])
                else:
                    mod = importlib.import_module(mod_name)
                for name, obj in inspect.getmembers(mod):
                    if inspect.isclass(obj) and issubclass(obj, Plugin) and obj is not Plugin:
                        instance = obj()
                        instance.on_load(None)
                        self.plugins.append(instance)
                        loaded += 1
            except Exception as e:
                print(f"Plugin load error ({f.name}): {e}", file=sys.stderr)
                traceback.print_exc()
        return loaded

    def register_hook(self, event, handler):
        if event not in self._hook_registry:
            self._hook_registry[event] = []
        self._hook_registry[event].append(handler)

    def trigger(self, event, *args, **kwargs):
        results = []
        for plugin in self.plugins:
            handler = getattr(plugin, f"on_{event}", None)
            if handler:
                try:
                    result = handler(*args, **kwargs)
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    print(f"Plugin hook error ({plugin.name}.on_{event}): {e}", file=sys.stderr)
        for handler in self._hook_registry.get(event, []):
            try:
                result = handler(*args, **kwargs)
                if result is not None:
                    results.append(result)
            except Exception as e:
                print(f"Registered hook error ({event}): {e}", file=sys.stderr)
        return results

    def unload_all(self):
        for plugin in self.plugins:
            try:
                plugin.on_unload(None)
            except Exception:
                pass
        self.plugins.clear()
        self._hook_registry.clear()
