# plagiarism_checker

![GIF demo](img/example.gif)

## About
This program will proccess pdf, txt, docx, and txt files that can be found in the given input directory, find similar sentences, calculate similarity percentage, display a similarity table with links to side by side comparison where similar sentences are highlighted.

This project was made part of my internship at the "Human Computer Humans Interacting with Computers at University of Primorska" lab (HICUP Lab).

**Usage**
---

```
Usage: main.py input_directory [OPTIONS]

  Perform a similarity analysis of all text files available in given input directory.
  Developped by Clément Delteil -> (Github: wazzabeee)


Options:
  -block_size, -s  Set minimum number of consecutive and similar words detected
  -out_dir, -o     Set the output directory for html files.
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
$ pip3 install requirements.txt

# Run the app
$ python main.py C:/Users/Desktop/papers -s 2 -o C:/Users/Desktop/results
```
