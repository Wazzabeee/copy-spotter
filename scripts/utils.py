from os import path
from time import sleep

from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer


def is_float(value: float) -> bool:
    """ Return true if value is a float and not equal to -1 """

    try:
        tmp = float(value)
        return True if tmp != -1 else False
    except ValueError:
        return False


def pretty_table(scores: list, names: list) -> None:
    """ Print similarity results nicely """

    row_format = "{:>15}" * (len(names) + 1)
    print(row_format.format("", *names))
    for name, row in zip(names, scores):
        print(row_format.format(name, *row))


def wait_for_file(file_path: str, timeout: int = 10) -> bool:
    """ Wait for the creation of a specific file.

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
    """ Remove all numbers from strings list to avoid errors """

    temp = [w for w in words_list if not isinstance(w, int)]
    return [w for w in temp if not isinstance(w, float)]


def remove_stop_words(words_list: list) -> list:
    """ Remove stop words from strings list """

    en_stop_words = set(stopwords.words('english'))

    return [w for w in words_list if str(w).lower not in en_stop_words]


def lemmatize(words_list: list) -> list:
    """ Return lemmatized words list """

    lemmatizer = WordNetLemmatizer()

    return [lemmatizer.lemmatize(w) for w in words_list]
