import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/charlieegan3/lennys-podcast-transcripts.git"

def main():
    root_dir = Path(__file__).resolve().parent.parent.parent
    target_dir = root_dir / "lennys-podcast-transcripts"

    if target_dir.exists() and (target_dir / ".git").exists():
        print(f"Transcripts repository already exists at {target_dir}. Pulling latest changes...")
        subprocess.run(["git", "-C", str(target_dir), "pull"], check=True)
    else:
        print(f"Cloning transcripts repository to {target_dir}...")
        subprocess.run(["git", "clone", REPO_URL, str(target_dir)], check=True)

    print("Transcripts repository is ready.")

if __name__ == "__main__":
    main()
