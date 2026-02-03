import os
import subprocess

if __name__ == "__main__":
    for directory in os.listdir("tmp"):
        if not "cookiecutter" in directory:
            continue
        dir_path = os.path.join("tmp", directory)
        if os.path.isdir(dir_path):
            tests4py_venv = os.path.join(dir_path, "tests4py_venv")
            if os.path.exists(tests4py_venv):
                bin_path = os.path.join(tests4py_venv, "bin", "python")
                if os.path.exists(bin_path):
                    result = subprocess.run(
                        [bin_path, "-m", "pip", "install", "pytest-cov==4.0.0"],
                        capture_output=True,
                        text=True,
                    )
                    print(
                        f"Uninstalled pytest-cov in {dir_path}:\n{result.stdout}\n{result.stderr}"
                    )
