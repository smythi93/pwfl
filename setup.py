import subprocess
from pathlib import Path

DIR = Path(__file__).parent.resolve()

if __name__ == "__main__":
    subprocess.run(["python3", "-m", "pip", "install", "-r", DIR / "requirements.txt"])
    subprocess.run(["python3", "-m", "pip", "install", DIR / "sflkit"])
    subprocess.run(["python3", "-m", "pip", "install", DIR / "sflkit-lib"])
