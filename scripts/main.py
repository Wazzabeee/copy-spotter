import os
import sys
import difflib
from tabulate import tabulate
from os import listdir, fsync, rename
import webbrowser
from bs4 import BeautifulSoup as Bs
from processing_files import *
from random import randint
from operator import itemgetter
from utils import remove_numbers, remove_stop_words, lemmatize, wait_for_file
from bs4_html import add_links_to_html_table
from datetime import datetime
from shutil import copy

# TODO Implement Cosine Similarity


def pretty_table(scores: list, names: list) -> None:
    """ Print similarity results nicely """

    row_format = "{:>15}" * (len(names) + 1)
    print(row_format.format("", *names))
    for name, row in zip(names, scores):
        print(row_format.format(name, *row))


def difflib_overlap(word_token1: list, word_token2: list) -> float:
    """ Get similarity percentage from matching sequences between two strings """

    seq = difflib.SequenceMatcher(a=word_token1, b=word_token2)

    # Return similarity percentage based on difflib library Sequence Matcher
    return round(seq.ratio() * 100, 3)


def calculate_overlap(word_token1: list, word_token2: list) -> float:
    """ Get similarity percentage from usage of similar words in two strings """

    overlapping_words = []

    for w in word_token1:
        if w in word_token2:
            overlapping_words.append(w)

    overlap_percentage = len(overlapping_words) / len(word_token1) * 100

    return round(overlap_percentage, 3)


def calculate_jaccard(word_tokens1: list, word_tokens2: list) -> float:
    """ Calculates intersection over union and return Jaccard similarity score """

    list1, list2 = remove_numbers(word_tokens1), remove_numbers(word_tokens2)
    list1, list2 = remove_stop_words(list1), remove_stop_words(list2)
    list1, list2 = lemmatize(list1), lemmatize(list2)

    # Combine both tokens to find union
    both_tokens = list1 + list2
    union = set(both_tokens)

    # Calculate intersection
    intersection = set()
    for w in list1:
        if w in list2:
            intersection.add(w)

    jaccard_score = len(intersection) / len(union)

    return round(jaccard_score, 3)


def get_real_matching_blocks(words_list1: list, words_list2: list, n: int) -> list:
    """ Return list of matching blocks with size greater than n """

    matching_blocks = difflib.SequenceMatcher(a=words_list1, b=words_list2).get_matching_blocks()

    return [b for b in matching_blocks if b.size > n]


def get_ordered_blocks_positions(string: str, matching_blocks: list, string_blocks: list) -> list:
    """ Return ordered list of all positions of matching blocks in string """

    all_blocks_positions = []

    for block_ind, block in enumerate(matching_blocks):
        # Find all positions of substring in string
        block_positions = [char for char in range(len(string)) if string.startswith(string_blocks[
                                                                                   block_ind],
                                                                              char)]
        for position in block_positions:
            all_blocks_positions.append((position, block_ind))

    return sorted(all_blocks_positions, key=itemgetter(0))


def blocks_list_to_strings_list(blocks_list: list, curr_text: list) -> list:
    """ Convert blocks list to len of blocks strings """

    strings_len_list = []

    for block in blocks_list:
        # Append size of block in string
        strings_len_list.append(len(' '.join(map(str, curr_text[block.a:block.a + block.size]))))

    return strings_len_list


def get_span_blocks(bs_obj: Bs, text1: list, text2: list) -> list:
    """ Return list of spans with colors for HTML rendering """

    results = [[], []]  # List of spans list

    # Get matching blocks with size greater than 2
    matching_blocks = get_real_matching_blocks(text1, text2, 2)

    # Generate one unique color for each matching block
    colors = ['#%06X' % randint(0, 0xFFFFFF) for _ in range(len(matching_blocks))]

    # Convert blocks from list of list of strings to list of strings
    string_blocks = [' '.join(map(str, text1[b.a:b.a + b.size])) for b in matching_blocks]

    # Store lengths of blocks in text
    strings_len_list = blocks_list_to_strings_list(matching_blocks, text1)

    # Convert list of strings to strings
    str1, str2 = ' '.join(map(str, text1)), ' '.join(map(str, text2))

    global_positions_list = [get_ordered_blocks_positions(str1, matching_blocks,
                                                          string_blocks),
                             get_ordered_blocks_positions(str2, matching_blocks,
                                                          string_blocks)]

    for num, pos_list in enumerate(global_positions_list):
        cursor = 0  # Cursor on current string

        if num == 1:  # Second iteration on second string
            str1 = str2

        for block in pos_list:
            # Span tag for the text before the matching sequence
            span = bs_obj.new_tag('span')
            span.string = str1[cursor:block[0]]

            # Span tag for the text in the matching sequence
            blockspan = bs_obj.new_tag('span',
                                       style="color:" + colors[block[1]] + "; font-weight:bold")
            blockspan.string = str1[block[0]:block[0] + strings_len_list[block[1]]]

            # Append spans tags to results list
            results[num].append(span)
            results[num].append(blockspan)

            # Update cursor position after last matching sequence
            cursor = block[0] + strings_len_list[block[1]]

        # End of loop, last span tag for the rest of the text
        span = bs_obj.new_tag('span')
        span.string = str1[cursor:]
        results[num].append(span)

    return results


def papers_comparison(save_dir: str, ind: int, text1: list, text2: list) -> None:
    """ """

    copy(r'..\templates\template.html', save_dir)   # Copy comparison template to curr dir
    comp_path = path.join(save_dir, str(ind) + '.html')
    rename(path.join(save_dir, 'template.html'), comp_path)

    html = open(comp_path)
    soup = Bs(html, 'html.parser')

    res = get_span_blocks(soup, text1, text2)

    blocks = soup.findAll(attrs={'class': 'block'})
    for tag in res[0]:
        blocks[0].append(tag)
    for tag in res[1]:
        blocks[1].append(tag)

    with open(comp_path, 'wb') as f_output:
        f_output.write(soup.prettify("utf-8"))


def results_to_html(scores: list, files_names: list, html_path: str) -> None:
    """  Write similarity results to HTML page """

    for ind in range(len(files_names)):
        scores[ind].insert(0, files_names[ind])

    scores.insert(0, files_names)
    scores[0].insert(0, '')

    with open(html_path, 'w') as f:
        f.write(tabulate(scores, tablefmt='html'))
        f.flush()
        fsync(f.fileno())
        f.close()


def writing_results(dir_name: str) -> str:
    """ Create new directory for results in current working directory """

    curr_directory = os.getcwd()
    final_directory = os.path.join(curr_directory, r'' + dir_name)
    if not os.path.exists(final_directory):
        os.makedirs(final_directory)

    return final_directory


if __name__ == '__main__':

    arg = sys.argv
    print(arg)
    if len(arg) >= 3:

        student_papers = sys.argv[1]
        main_paper = sys.argv[2]

        if path.exists(student_papers) and path.isfile(main_paper):
            processed_files = [file_extension_call(main_paper)]

            if processed_files[0] is not None:

                filenames = ['reference']
                for filename in listdir(student_papers):
                    if path.isfile(student_papers + '\\' + filename):
                        processed_files.append(
                            file_extension_call(student_papers + '\\' + filename))
                        filenames.append(filename)

                # jaccard_scores = [[] for _ in range(len(processed_files))]
                # overlap_scores = [[] for _ in range(len(processed_files))]
                res_dir = writing_results(datetime.now().strftime("%Y%m%d_%H%M%S"))
                difflib_scores = [[] for _ in range(len(processed_files))]
                file_ind = 0

                for i, text in enumerate(processed_files):
                    for j, text_bis in enumerate(processed_files):
                        if i != j:
                            # jaccard_scores[i].append(calculate_jaccard(text, text_bis))
                            # overlap_scores[i].append(calculate_overlap(text, text_bis))
                            difflib_scores[i].append(difflib_overlap(text, text_bis))
                            papers_comparison(res_dir, file_ind, text, text_bis)
                            file_ind += 1
                        else:
                            # jaccard_scores[i].append(-1)
                            # overlap_scores[i].append(-1)
                            difflib_scores[i].append(-1)

                # print("\n \n Jaccard similarity \n")
                # pretty_table(jaccard_scores, filenames)
                # print("\n \n Percentage of overlapping \n")
                # pretty_table(overlap_scores, filenames)
                # print("\n \n Percentage of matching sequences from difflib \n")
                # pretty_table(difflib_scores, filenames)

                res_dir = path.join(res_dir, '_results.html')
                print(res_dir)
                print(path.isfile(res_dir))
                results_to_html(difflib_scores, filenames, res_dir)
                if wait_for_file(res_dir, 60):
                    add_links_to_html_table(res_dir)
                    webbrowser.open(res_dir)
                else:
                    print("Results file was not created...")
        else:
            print("Check main paper format")
            exit()

    else:
        """
        p1 = "C:\\Users\\Clément\\Downloads\\real_student_reports\\students\\p6.docx"
        p2 = "C:\\Users\\Clément\\Downloads\\real_student_reports\\students\\p7.pdf"

        s1 = file_extension_call(p1)
        s2 = file_extension_call(p2)

        html = open(r'..\templates\template.html')
        soup = Bs(html, 'html.parser')

        res = get_span_blocks(soup, s1, s2)

        blocks = soup.findAll(attrs={'class': 'block'})
        for tag in res[0]:
            blocks[0].append(tag)
        for tag in res[1]:
            blocks[1].append(tag)

        with open(r'..\templates\template.html', 'wb') as f_output:
            f_output.write(soup.prettify("utf-8"))
        """
        print("Missing mandatory parameters")
        print("python script.py  full_path_to_student_files_directory full_path_to_reference_file ")
