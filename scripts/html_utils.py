""" This script stores useful functions for html_writing.py file

It finds occurences of matching blocks in text.
It gets ordered positions of matching blocks in text.
It returns colors depending on the similarity score.

"""

import difflib
from operator import itemgetter
from typing import List, Tuple
from os import getcwd, path, makedirs


def get_real_matching_blocks(words_list1: list, words_list2: list, minimum_size: int = 2) -> list:
    """Return list of matching blocks with size greater than n"""

    matching_blocks = difflib.SequenceMatcher(a=words_list1, b=words_list2).get_matching_blocks()
    if minimum_size and minimum_size > 0:
        return [b for b in matching_blocks if b.size >= minimum_size]

    return [b for b in matching_blocks if b.size >= 2]


def get_ordered_blocks_positions(string: str, matching_blocks: list, string_blocks: list) -> list:
    """Return ordered list of all positions of matching blocks in string"""

    all_blocks_positions: List[Tuple[int, int]] = []

    for block_ind, _ in enumerate(matching_blocks):
        # Find all positions of substring in string
        block_positions = [char for char in range(len(string)) if string.startswith(string_blocks[block_ind], char)]

        for position in block_positions:
            # We check if there is another block starting at the same position
            var = [pos_tuple for pos_tuple in all_blocks_positions if pos_tuple[0] == position]
            if var:  # If there is one such block
                size = len(string_blocks[var[0][1]])  # get size of block in var
                if size < len(string_blocks[block_ind]):
                    # Remove old position block which is smaller than curr block
                    all_blocks_positions.pop(all_blocks_positions.index(var[0]))

                    # Add new block to list
                    all_blocks_positions.append((position, block_ind))
            else:
                all_blocks_positions.append((position, block_ind))

    return sorted(all_blocks_positions, key=itemgetter(0))


def blocks_list_to_strings_list(blocks_list: list, curr_text: list) -> list:
    """Convert blocks list to len of blocks strings"""

    strings_len_list = []

    for block in blocks_list:
        # Append size of block in string
        strings_len_list.append(len(" ".join(map(str, curr_text[block.a : block.a + block.size]))))

    return strings_len_list


def writing_results(dir_name: str) -> str:
    """Create new directory for results in current working directory"""

    curr_directory = path.dirname(getcwd())
    final_directory = path.join(curr_directory, r"results/" + dir_name)
    if not path.exists(final_directory):
        makedirs(final_directory)

    return final_directory


def get_color_from_similarity(similarity_score: float) -> str:
    """Return css style according to similarity score"""

    if float(similarity_score) > 15:
        return "#990033; font-weight: bold"
    if float(similarity_score) > 10:
        return "#ff6600"
    if float(similarity_score) > 5:
        return "#ffcc00"

    return "green"
