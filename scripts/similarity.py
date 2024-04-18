""" This function calculates similarity scores with different methods

It calculates similarity scores with :
- difflib library to find matching sequences.
- Jaccard Similarity
- words counting,
- overlapping words

"""

import difflib

from scripts.utils import remove_numbers, remove_stop_words, lemmatize


def difflib_overlap(word_token1: list, word_token2: list) -> float:
    """Get similarity percentage from matching sequences between two strings"""

    seq = difflib.SequenceMatcher(a=word_token1, b=word_token2)

    # Return similarity percentage based on difflib library Sequence Matcher
    return round(seq.ratio() * 100, 3)


def calculate_overlap(word_token1: list, word_token2: list) -> float:
    """Get similarity percentage from usage of similar words in two strings"""

    overlapping_words = []

    for word in word_token1:
        if word in word_token2:
            overlapping_words.append(word)

    overlap_percentage = len(overlapping_words) / len(word_token1) * 100

    return round(overlap_percentage, 3)


def calculate_jaccard(word_tokens1: list, word_tokens2: list) -> float:
    """Calculates intersection over union and return Jaccard similarity score"""

    list1, list2 = remove_numbers(word_tokens1), remove_numbers(word_tokens2)
    list1, list2 = remove_stop_words(list1), remove_stop_words(list2)
    list1, list2 = lemmatize(list1), lemmatize(list2)

    # Combine both tokens to find union
    both_tokens = list1 + list2
    union = set(both_tokens)

    # Calculate intersection
    intersection = set()
    for word in list1:
        if word in list2:
            intersection.add(word)

    jaccard_score = len(intersection) / len(union)

    return round(jaccard_score, 3)
