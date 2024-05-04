#!/usr/bin/env python
""" This module launches the files comparison process

This modules compares all txt, docs, odt, pdf files present in path specified as argument.
It writes results in a HTML table.
It uses difflib library to find matching sequences.
It can also use Jaccard Similarity, words counting, overlapping words for similarity

"""
import webbrowser
from datetime import datetime
from os import listdir, path
from typing import List

from tqdm import tqdm

from scripts.html_writing import add_links_to_html_table, results_to_html, papers_comparison
from scripts.html_utils import writing_results
from scripts.processing_files import file_extension_call
from scripts.similarity import difflib_overlap
from scripts.utils import wait_for_file, parse_options


class MinimumFilesError(Exception):
    """Raised when there are fewer than two files for comparison."""

    pass


class UnsupportedFileError(Exception):
    """Raised when there are unsupported files in the input directory."""

    pass


class PathNotFoundError(Exception):
    """Raised when the specified input directory path does not exist."""

    pass


def main() -> None:
    """
    Main function to process and compare text files.

    Parses command-line arguments to obtain input and output directories and block size for comparison.
    Validates the input directory and checks if there are at least two files for comparison.
    Processes each file in the input directory, extracting text and handling different file formats.
    Calculates similarity scores between each pair of processed files using difflib.
    Generates and writes HTML files with colored comparison results in the specified output directory.
    Creates a summary results HTML file with links to individual comparisons and opens it in a web browser.
    Exits the program if the specified path does not exist, or if there are fewer than two files for comparison.
    """

    args = parse_options()
    in_dir, out_dir, block_size = args.in_dir, args.out_dir, args.block_size

    if not path.exists(in_dir):
        raise PathNotFoundError(f"The specified path does not exist: {in_dir}")

    if not path.isabs(in_dir):
        in_dir = path.abspath(in_dir)

    files = [
        f for f in listdir(in_dir) if path.isfile(path.join(in_dir, f)) and f.endswith(("txt", "pdf", "docx", "odt"))
    ]

    if len(files) < 2:
        raise MinimumFilesError(
            "Minimum number of files is not present. Please check that there are at least two files to compare."
        )

    filenames, processed_files = [], []

    for file in tqdm(files, desc="Processing Files"):
        file_words = file_extension_call(str(path.join(in_dir, file)))
        if file_words:  # If all files have supported format
            processed_files.append(file_words)
            filenames.append(path.splitext(file)[0])
        else:
            raise UnsupportedFileError("Remove files which are not txt, pdf, docx, or odt and run the script again.")

    if out_dir is not None and path.exists(out_dir):
        if not path.isabs(out_dir):
            out_dir = path.abspath(out_dir)
        results_directory = out_dir
    else:
        results_directory = writing_results(datetime.now().strftime("%Y%m%d_%H%M%S"))

    difflib_scores: List[List[float]] = [[] for _ in range(len(processed_files))]
    file_ind = 0

    for i, text in enumerate(tqdm(processed_files, desc="Comparing Files")):
        for j, text_bis in enumerate(processed_files):
            if i != j:
                difflib_scores[i].append(difflib_overlap(text, text_bis))
                papers_comparison(
                    results_directory,
                    file_ind,
                    text,
                    text_bis,
                    (filenames[i], filenames[j]),
                    block_size,
                )
                file_ind += 1
            else:
                difflib_scores[i].append(-1)

    results_directory = path.join(results_directory, "_results.html")
    print(f"Results saved at: {results_directory}")

    results_to_html(difflib_scores, filenames, results_directory)

    if wait_for_file(results_directory, 60):  # Wait for file to be created
        add_links_to_html_table(results_directory)
        webbrowser.open(results_directory)  # Open results HTML table
    else:
        raise RuntimeError("Results file was not created...")


if __name__ == "__main__":
    main()
