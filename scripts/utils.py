""" This script stores functions for text processing, type validation, printing results

It verifies if value is float different from - 1
It prints similarity results in a pretty table in console
It waits for file creation
It can lemmatize, remove stop words, remove numbers for text processing

"""

import argparse
from os import path, listdir
from time import sleep
from typing import Any

from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer


def parse_options():
    """
    Parses command-line arguments for the script.

    This function sets up an argument parser for the script, specifying the required input directory
    and optional output directory and block size arguments.

    Args:
    None

    Returns:
    argparse.Namespace: The parsed command-line arguments, where 'in_dir' is the input directory,
    'out_dir' is the optional output directory, and 'block_size' is the optional minimum number of
    consecutive similar words for block comparison (default is 2).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("in_dir", type=str, help="input directory for text files")
    parser.add_argument("-o", "--out_dir", type=str, help="output directory for html results files")
    parser.add_argument(
        "-s",
        "--block_size",
        type=int,
        help="minimum number of consecutive and " "similar words detected (default=2)",
    )

    return parser.parse_args()


def is_float(value: Any) -> bool:
    """Return true if value is a float and not equal to -1."""
    try:
        return float(value) != -1
    except ValueError:
        return False


def get_student_names(main_path):
    """
    Extracts student names from the directory names within the specified main path.

    This function assumes that each sub-directory within the main path represents a student and
    that the student's name is the first part of the sub-directory name, delimited by an underscore.

    Args:
    main_path (str): The path of the main directory containing student sub-directories.

    Returns:
    list: A list of student names extracted from the sub-directory names.
    """
    sub_directories = [name for name in listdir(main_path) if path.isdir(path.join(main_path, name))]

    return [title.split("_")[0] for title in sub_directories]


def pretty_table(scores: list, names: list) -> None:
    """Print similarity results nicely"""

    row_format = "{:>15}" * (len(names) + 1)
    print(row_format.format("", *names))
    for name, row in zip(names, scores):
        print(row_format.format(name, *row))


def wait_for_file(file_path: str, timeout: int = 10) -> bool:
    """Wait for the creation of a specific file.

    This method checks if the specified file exists and waits for it to
    appear during the specified amount of time (by default 10 seconds).

    filepath[in]    Fullpath to the file to wait for
    timeout[in]     Time to wait in seconds (by default 10 seconds).
    """

    attempts = 0
    while attempts < timeout:
        # Check if the file exists.
        if path.isfile(file_path):
            return True
        # Wait 1 second before trying again.
        sleep(1)
        attempts += 1

    return False


def remove_numbers(words_list: list) -> list:
    """Remove all numbers from strings list to avoid errors"""

    temp = [w for w in words_list if not isinstance(w, int)]
    return [w for w in temp if not isinstance(w, float)]


def remove_stop_words(words_list: list) -> list:
    """Remove stop words from strings list"""

    en_stop_words = set(stopwords.words("english"))

    return [w for w in words_list if str(w).lower() not in en_stop_words]


def lemmatize(words_list: list) -> list:
    """Return lemmatized words list"""

    lemmatizer = WordNetLemmatizer()

    return [lemmatizer.lemmatize(w) for w in words_list]
