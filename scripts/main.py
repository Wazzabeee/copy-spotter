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

from html import add_links_to_html_table, results_to_html, papers_comparison
from html_utils import writing_results
from processing_files import file_extension_call
from similarity import difflib_overlap
from utils import wait_for_file

if __name__ == '__main__':

    arg = sys.argv
    print(arg)
    if len(arg) >= 2:  # Check that user gave enough parameters

        papers = sys.argv[1]

        if path.exists(papers):  # Check if specified path exists

            if len(listdir(papers)) > 1:  # Check if there are at least 2 files at specified path

                filenames, processed_files = [], []
                for filename in listdir(papers):  # We loop trough files in directory

                    if path.isfile(papers + '\\' + filename):
                        # We parse the file with the appropriate function
                        file_words = file_extension_call(papers + '\\' + filename)

                        if file_words:  # If all files have supported format
                            processed_files.append(file_words)
                            filenames.append(filename)
                        else:  # At least one file was not supported
                            print("Remove files which are not txt, pdf, docx or odt and run the "
                                  "script again.")
                            sys.exit()

                # Create new directory for storing html files
                results_directory = writing_results(datetime.now().strftime("%Y%m%d_%H%M%S"))

                difflib_scores = [[] for _ in range(len(processed_files))]
                file_ind = 0

                for i, text in enumerate(processed_files):
                    for j, text_bis in enumerate(processed_files):
                        if i != j:
                            # Append to the list the similarity score between text and text_bis
                            difflib_scores[i].append(difflib_overlap(text, text_bis))

                            # Write text with matching blocks colored in results directory
                            papers_comparison(results_directory, file_ind, text, text_bis)
                            file_ind += 1
                        else:
                            difflib_scores[i].append(-1)

                results_directory = path.join(results_directory, '_results.html')
                print(results_directory)

                results_to_html(difflib_scores, filenames, results_directory)

                if wait_for_file(results_directory, 60):  # Wait for file to be created
                    add_links_to_html_table(results_directory)
                    webbrowser.open(results_directory)  # Open results HTML table
                else:
                    print("Results file was not created...")
            else:
                print(
                    "Minimum number of files is not present. Please check that there are at least "
                    "two files to compare.")
                sys.exit()
        else:
            print("The specified path does not exist : " + papers)
            sys.exit()

    else:
        print("Missing mandatory parameters")
        print("python main.py full_path_to_papers_directory")
        sys.exit()
