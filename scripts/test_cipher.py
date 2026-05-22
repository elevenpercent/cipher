"""
Cipher test launcher — opens Cipher in a new terminal window for manual testing.
Usage:  python scripts/test_cipher.py [project_dir]
"""
import os
import sys
import subprocess
import tempfile

def main():
    project_dir = sys.argv[1] if len(sys.argv) > 1 else None
    if project_dir is None:
        project_dir = os.path.join(tempfile.gettempdir(), "cipher-test")
        os.makedirs(project_dir, exist_ok=True)
        print(f"Using temp project dir: {project_dir}")
    else:
        project_dir = os.path.abspath(project_dir)

    print(f"Launching Cipher in: {project_dir}")

    if sys.platform == "win32":
        # Try Windows Terminal first, fall back to cmd
        wt = subprocess.run(["where", "wt"], capture_output=True, text=True)
        if wt.returncode == 0:
            cmd = f'wt -d "{project_dir}" -- cip'
        else:
            cmd = f'start cmd /k "cd /d "{project_dir}" && cip"'
        subprocess.Popen(cmd, shell=True)
    else:
        # macOS / Linux — open in a new terminal
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Terminal", project_dir])
        else:
            for term in ("gnome-terminal", "xterm", "konsole"):
                if subprocess.run(["which", term], capture_output=True).returncode == 0:
                    subprocess.Popen([term, "--working-directory", project_dir, "-e", "cip"])
                    break

    print("Cipher window opened. Switch to it and start testing.")
    print(f"Project dir: {project_dir}")

if __name__ == "__main__":
    main()
