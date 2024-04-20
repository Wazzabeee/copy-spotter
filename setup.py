from setuptools import setup, find_packages

with open("VERSION") as version_file:
    version = version_file.read().strip()

setup(
    name="plagiarism-checker",
    version=version,
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
    url="https://github.com/Wazzabeee/plagiarism_checker",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
    ],
    python_requires=">=3.10",
)
