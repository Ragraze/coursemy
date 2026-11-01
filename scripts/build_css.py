"""Build Tailwind with its standalone CLI; no Node project is required."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
VERSION = "v4.1.17"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(platform.system())
    machine = {"x86_64": "x64", "AMD64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine())
    if (not system or not machine) and not os.environ.get("TAILWIND_BIN"):
        parser.error("Unsupported platform; set TAILWIND_BIN to a standalone Tailwind binary.")
    suffix = ".exe" if system == "windows" else ""
    asset = f"tailwindcss-{system}-{machine}{suffix}"
    binary = Path(os.environ.get("TAILWIND_BIN", ROOT / ".tools" / f"tailwindcss-{VERSION}{suffix}"))
    if not binary.is_file():
        binary.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/{VERSION}/{asset}"
        print(f"Downloading standalone Tailwind {VERSION} from GitHub...")
        temporary = binary.with_suffix(".download")
        try:
            with urllib.request.urlopen(url, timeout=60) as source, temporary.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            temporary.chmod(0o755)
            temporary.replace(binary)
        except (urllib.error.URLError, OSError) as exc:
            parser.exit(1, f"Tailwind CLI tidak dapat diunduh: {exc}. Sediakan TAILWIND_BIN atau coba lagi dengan akses jaringan.\n")
        finally:
            temporary.unlink(missing_ok=True)
    command = [str(binary.resolve()), "-i", "app/static/css/input.css", "-o", "app/static/css/style.css", "--minify"]
    if args.watch:
        command.append("--watch")
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        parser.exit(1, f"Build Tailwind gagal: {exc}\n")


if __name__ == "__main__":
    main()
