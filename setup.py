import subprocess
import logging
from setuptools import setup, find_packages


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def get_version(default="0.1.0"):
    try:
        version = subprocess.check_output(["git", "describe", "--tags", "--long"]).strip().decode("utf-8")
        logging.info(f"Original version from git: {version}")

        if "-" in version:
            # Example output: v0.1.0-3-gaf8ca44
            # Convert to PEP 440 compliant version without local version identifiers
            parts = version.split("-")
            base_version = parts[0]  # 'v0.1.0'
            commit_count = parts[1]  # '3'

            # Remove leading 'v' and split version components
            major, minor, patch = map(int, base_version.lstrip("v").split("."))

            # Increment patch version by commit count
            patch += int(commit_count)
            version = f"{major}.{minor}.{patch}"
            logging.info(f"Normalized version for PyPI: {version}")
    except Exception:
        logging.error("Failed to get version from git, using default version.", exc_info=True)
        version = default
    return version


setup(
    name="copy-spotter",
    version=get_version(),
    packages=find_packages(),
    install_requires=[
        "beautifulsoup4==4.10.0",
        "nltk==3.6.6",
        "odfpy==1.4.1",
        "pdfplumber==0.5.28",
        "slate3k==0.5.3",
        "tabulate==0.8.9",
    ],
    extras_require={
        "lint": ["pylint==3.0.2", "mypy==1.7.1", "flake8==6.1.0", "black==24.3.0", "types-tabulate"],
        "dev": ["pytest", "pre-commit"],
    },
    author="Clément Delteil",
    author_email="clement45.delteil45@gmail.com",
    description="Make plagiarism detection easier. This package will find similar sentences between given files and "
    "highlight them in a side by side comparison.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/Wazzabeee/copy-spotter",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "copy-spotter=scripts.main:main",
        ],
    },
)
