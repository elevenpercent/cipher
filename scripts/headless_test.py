"""
Headless test harness for Cipher TUI.
Drives the app with a mock AI provider — no real terminal, no API calls.

Usage:
    python scripts/headless_test.py [output_dir]
    python scripts/headless_test.py C:/Projects/Cipher/test-output
"""
import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = str(Path(__file__).parent.parent)
sys.path.insert(0, ROOT)

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "C:/Projects/Cipher/test-output"

# ---------------------------------------------------------------------------
# Mock AI responses — add more scenarios here
# ---------------------------------------------------------------------------

SCENARIOS = {
    "write_file": (
        "create a file called hi.py that prints hello",
        "Writing the file now.\n"
        "<write path=\"hi.py\">print('hello')\n</write>\n"
        "Running it to confirm.\n"
        "<run>python hi.py</run>\n"
        "<done>Created hi.py — it prints hello</done>"
    ),
    "edit_file": (
        "add a goodbye line to hi.py",
        "Reading the file first.\n"
        "<read path=\"hi.py\">\n"
        "Now editing it.\n"
        "<edit path=\"hi.py\"><old>print('hello')</old><new>print('hello')\nprint('goodbye')</new></edit>\n"
        "<done>Added goodbye line to hi.py</done>"
    ),
    "greeting": (
        "hello",
        "Hey! I'm Cipher, your autonomous coding agent. "
        "Tell me what you want to build and I'll get it done."
    ),
    "git_status": (
        "check git status",
        "Checking the repo status.\n"
        "<git status>\n"
        "<done>Showed git status</done>"
    ),
}


def make_mock_chat(response_text: str):
    def mock_chat(self, messages, stream=True):
        for char in response_text:
            yield {"content": char}
    return mock_chat


async def run_scenario(name: str, message: str, response: str):
    project_dir = tempfile.mkdtemp(prefix=f"cipher-test-{name}-")
    os.makedirs(OUT_DIR, exist_ok=True)

    # Patch before importing CipherApp so the mock is in place when the class loads
    with patch("cipher.provider.AIProvider.chat", make_mock_chat(response)):
        # Import fresh each run
        if "cipher.app" in sys.modules:
            del sys.modules["cipher.app"]
        from cipher.app import CipherApp

        app = CipherApp(project_root=project_dir)
        screenshots = []

        async def autopilot(pilot):
            # Wait for mount
            await pilot.pause(1.5)
            app.save_screenshot(f"{OUT_DIR}/{name}-01-startup.svg")
            screenshots.append(f"{name}-01-startup.svg")

            # Send the test message by setting the Input value directly
            inp = app.query_one("#chat-input")
            inp.value = message
            await pilot.press("enter")

            # Wait for the agent loop to complete
            await pilot.pause(6.0)
            app.save_screenshot(f"{OUT_DIR}/{name}-02-response.svg")
            screenshots.append(f"{name}-02-response.svg")

            # Test: expand a tool result if any
            tool_widgets = app.query(".msg-tool")
            if tool_widgets:
                await pilot.click(tool_widgets.first())
                await pilot.pause(0.5)
                app.save_screenshot(f"{OUT_DIR}/{name}-03-tool-expanded.svg")
                screenshots.append(f"{name}-03-tool-expanded.svg")

            await pilot.exit(0)

        await app.run_async(headless=True, auto_pilot=autopilot, size=(200, 50))
        return screenshots


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_shots = []

    for name, (message, response) in SCENARIOS.items():
        print(f"  Running scenario: {name}")
        try:
            shots = await run_scenario(name, message, response)
            all_shots.extend(shots)
            print(f"    OK — {len(shots)} screenshots")
        except Exception as e:
            print(f"    FAIL: {e}")

    print(f"\nDone. {len(all_shots)} screenshots saved to {OUT_DIR}/")
    for s in all_shots:
        print(f"  {s}")


if __name__ == "__main__":
    asyncio.run(main())
