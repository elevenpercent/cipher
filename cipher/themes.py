import json
from pathlib import Path

THEMES_DIR = Path.home() / ".cipher" / "themes"


class Theme:
    def __init__(self, name, colors):
        self.name = name
        self.colors = colors

    def css(self):
        c = self.colors
        return f"""
Screen {{ background: {c['bg']}; }}
.msg-user {{ margin: 1 0; padding: 0 1; color: {c['accent']}; }}
.msg-assistant {{ margin: 1 0; padding: 0 1; color: {c['fg']}; }}
.msg-plan {{ margin: 1 0 1 2; }}
.msg-code {{ margin: 1 0 1 4; }}
.msg-tool {{ margin: 0 0 1 4; }}
.msg-explanation {{ margin: 1 0 1 2; }}
.msg-system {{ margin: 0 0 1 0; color: {c['muted']}; text-style: italic; }}
.cmd-block {{ margin: 1 0; padding: 0 1; }}
.loading-msg {{ margin: 0 0 1 4; color: {c['accent']}; }}
"""


DARK = Theme("dark", {
    "bg": "#050505",
    "fg": "#dddddd",
    "accent": "#f5c542",
    "muted": "#666666",
    "success": "#22c55e",
    "error": "#ef4444",
    "info": "#3b82f6",
    "warning": "#f59e0b",
})

LIGHT = Theme("light", {
    "bg": "#ffffff",
    "fg": "#1a1a1a",
    "accent": "#d97706",
    "muted": "#999999",
    "success": "#16a34a",
    "error": "#dc2626",
    "info": "#2563eb",
    "warning": "#d97706",
})

DRACULA = Theme("dracula", {
    "bg": "#282a36",
    "fg": "#f8f8f2",
    "accent": "#ff79c6",
    "muted": "#6272a4",
    "success": "#50fa7b",
    "error": "#ff5555",
    "info": "#8be9fd",
    "warning": "#f1fa8c",
})

SOLARIZED = Theme("solarized", {
    "bg": "#002b36",
    "fg": "#839496",
    "accent": "#b58900",
    "muted": "#586e75",
    "success": "#859900",
    "error": "#dc322f",
    "info": "#268bd2",
    "warning": "#cb4b16",
})

NORD = Theme("nord", {
    "bg": "#2e3440",
    "fg": "#d8dee9",
    "accent": "#88c0d0",
    "muted": "#4c566a",
    "success": "#a3be8c",
    "error": "#bf616a",
    "info": "#81a1c1",
    "warning": "#ebcb8b",
})

MONOKAI = Theme("monokai", {
    "bg": "#272822",
    "fg": "#f8f8f2",
    "accent": "#a6e22e",
    "muted": "#75715e",
    "success": "#a6e22e",
    "error": "#f92672",
    "info": "#66d9ef",
    "warning": "#e6db74",
})

GRUVBOX = Theme("gruvbox", {
    "bg": "#282828",
    "fg": "#ebdbb2",
    "accent": "#fabd2f",
    "muted": "#928374",
    "success": "#b8bb26",
    "error": "#fb4934",
    "info": "#83a598",
    "warning": "#fe8019",
})

TOKYO_NIGHT = Theme("tokyo-night", {
    "bg": "#1a1b26",
    "fg": "#c0caf5",
    "accent": "#7aa2f7",
    "muted": "#565f89",
    "success": "#9ece6a",
    "error": "#f7768e",
    "info": "#7dcfff",
    "warning": "#e0af68",
})

BUILTIN_THEMES = {
    "dark": DARK,
    "light": LIGHT,
    "dracula": DRACULA,
    "solarized": SOLARIZED,
    "nord": NORD,
    "monokai": MONOKAI,
    "gruvbox": GRUVBOX,
    "tokyo-night": TOKYO_NIGHT,
}


class ThemeManager:
    def __init__(self):
        self.current = DARK
        self.custom_themes = {}

    def set_theme(self, name):
        name = name.lower()
        if name in BUILTIN_THEMES:
            self.current = BUILTIN_THEMES[name]
            return True
        if name in self.custom_themes:
            self.current = self.custom_themes[name]
            return True
        return False

    def get_css(self):
        return self.current.css()

    def list_themes(self):
        result = {n: t.colors for n, t in BUILTIN_THEMES.items()}
        result.update({n: t.colors for n, t in self.custom_themes.items()})
        return result

    def discover(self):
        THEMES_DIR.mkdir(exist_ok=True)
        count = 0
        for f in THEMES_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = f.stem.lower()
                required = {"bg", "fg", "accent", "muted"}
                if required.issubset(data.keys()):
                    self.custom_themes[name] = Theme(name, data)
                    count += 1
            except Exception:
                pass
        return count
