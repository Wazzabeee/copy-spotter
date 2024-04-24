import subprocess
from setuptools import setup, find_packages


def get_version():
    return subprocess.check_output(["git", "describe", "--tags", "--abbrev=0"]).strip().decode("utf-8")[1:]


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
