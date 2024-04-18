#!/usr/bin/env python
""" This module launches the files comparison process

This modules compares all txt, docs, odt, pdf files present in path specified as argument.
It writes results in a HTML table.
It uses difflib library to find matching sequences.
It can also use Jaccard Similarity, words counting, overlapping words for similarity

"""
import sys
import webbrowser
from datetime import datetime
from os import listdir, path
from typing import List

from scripts.html_writing import add_links_to_html_table, results_to_html, papers_comparison
from scripts.html_utils import writing_results
from scripts.processing_files import file_extension_call
from scripts.similarity import difflib_overlap
from scripts.utils import wait_for_file, get_student_names, parse_options


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

    if path.exists(in_dir):  # Check if specified path exists
        if not path.isabs(in_dir):
            in_dir = path.abspath(in_dir)
        if len(listdir(in_dir)) > 1:  # Check if there are at least 2 files at specified path
            filenames, processed_files = [], []
            students_names = get_student_names(in_dir)
            for ind, direc in enumerate(listdir(in_dir)):
                if path.isdir(path.join(in_dir, direc)):
                    for file in listdir(path.join(in_dir, direc)):
                        file_words = file_extension_call(str(path.join(in_dir, direc, file)))

                        if file_words:  # If all files have supported format
                            processed_files.append(file_words)
                            filenames.append(students_names[ind])
                        else:  # At least one file was not supported
                            print("Remove files which are not txt, pdf, docx or odt and run the script again.")
                            sys.exit()
            if out_dir is not None and path.exists(out_dir):
                if not path.isabs(out_dir):
                    out_dir = path.abspath(out_dir)
                results_directory = out_dir
            else:
                # Create new directory for storing html files
                results_directory = writing_results(datetime.now().strftime("%Y%m%d_%H%M%S"))

            difflib_scores: List[List[float]] = [[] for _ in range(len(processed_files))]
            file_ind = 0

            for i, text in enumerate(processed_files):
                for j, text_bis in enumerate(processed_files):
                    if i != j:
                        # Append to the list the similarity score between text and text_bis
                        difflib_scores[i].append(difflib_overlap(text, text_bis))

                        # Write text with matching blocks colored in results directory
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
            print(results_directory)

            results_to_html(difflib_scores, filenames, results_directory)

            if wait_for_file(results_directory, 60):  # Wait for file to be created
                add_links_to_html_table(results_directory)
                webbrowser.open(results_directory)  # Open results HTML table
            else:
                print("Results file was not created...")
        else:
            print("Minimum number of files is not present. Please check that there are at least two files to compare.")
            sys.exit()
    else:
        print("The specified path does not exist : " + in_dir)
        sys.exit()


if __name__ == "__main__":
    main()
