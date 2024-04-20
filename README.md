# Plagiarism checker

![GIF demo](data/img/example.gif)

## About
This program will proccess pdf, txt, docx, and txt files that can be found in the given input directory, find similar sentences, calculate similarity percentage, display a similarity table with links to side by side comparison where similar sentences are highlighted.

This project was made part of my internship at the "Human Computer Humans Interacting with Computers at University of Primorska" lab (HICUP Lab).

**Usage**
---

```
Usage: python -m scripts.main.py input_directory [OPTIONS]

  Performs a similarity analysis of all text files available in given input directory.
  Developed by Clément Delteil -> (Github: Wazzabeee)

Options:
  -block_size, -s  Set minimum number of consecutive and similar words detected. (Default is 2)
  -out_dir, -o     Set the output directory for html files. (Default is creating a new directory)
  -help, -h        Show this message and exit.
```

**How to use**
---

```bash
# Clone this repository
$ git clone https://github.com/Wazzabeee/plagiarism_checker

# Go into the repository
$ cd plagiarism_checker

# Install requirements
$ pip install -r requirements.txt

# Run the app
$ python -m scripts.main.py data/pdf/plagiarism -s 2
```
**First run**
---
On the first run you might get :
- an ImportError from pdfminer library 
``` 
ImportError: cannot import name 'uint_value' from 'pdfminer.pdftypes' (C:/.../pdfminer/pdftypes.py)
```
To fix this, please uninstall pdfminer3k and pdfminer.six via 
``` pip uninstall pdfminer3k ```
``` pip uninstall pdfminer.six ```
Then install them again via 
``` pip install pdfminer3k ```
``` pip install pdfminer.six ```


- a TypeError from Slate3k library 
```
TypeError __init__() missing 1 required positional arg 'parser' in "C:/.../slate3k/classes.py
```
To fix this you'll need to modify `class PDF(list):` in `C:/.../slate3k/classes.py`. In `def __init__()` change both `if PYTHON 3:` <br/> to `if not PYTHON 3:` on lines 58 and 72.

**Recommandations**
---
- Please make sure that all text files are closed before running the program.
- In order to get the best results please provide text files of the same languages.
- Pdf files that are made from scanned images won't be processed correctly.
- If a specific file is not processed correctly feel free to [contact me](mailto:<clement45.delteil45@gmail.com>) so that I can address the issue.

**TODO**
---
- Add more tests
- Add info in console for timing (tqdm)
- Add CSS to HTML Template
- Fix Slate3k by installing custom fork