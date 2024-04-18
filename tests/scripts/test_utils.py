import unittest
from unittest.mock import patch
import nltk
from scripts.utils import (
    parse_options,
    is_float,
    wait_for_file,
    remove_numbers,
    remove_stop_words,
    lemmatize,
)


class TestUtils(unittest.TestCase):
    """
    Tests utils.py
    """

    @classmethod
    def setUpClass(cls):
        """
        Sets up the test class.
        """
        # Download NLTK stopwords
        nltk.download("stopwords")

    def test_parse_options(self):
        """
        Tests parse_options()
        """
        # Mock the arguments and test the parse_options function
        test_args = ["program", "input_dir", "-o", "output_dir", "-s", "5"]
        with patch("sys.argv", test_args):
            args = parse_options()
            self.assertEqual(args.in_dir, "input_dir")
            self.assertEqual(args.out_dir, "output_dir")
            self.assertEqual(args.block_size, 5)

    def test_is_float(self):
        """
        Tests is_float()
        """
        # Test cases for is_float function
        self.assertTrue(is_float(3.14))
        self.assertFalse(is_float(-1))
        self.assertFalse(is_float("not a float"))

    def test_wait_for_file(self):
        """
        Tests wait_for_file()
        """
        # Test the wait_for_file function with a mock path.isfile
        with patch("os.path.isfile", return_value=True):
            self.assertTrue(wait_for_file("dummy_file"))

    def test_remove_numbers(self):
        """
        Tests remove_numbers()
        """
        # Test the remove_numbers function
        words_list = ["hello", "world", 123, 4.56]
        expected = ["hello", "world"]
        self.assertEqual(remove_numbers(words_list), expected)

    def test_remove_stop_words(self):
        """
        Tests remove_stop_words()
        """
        # Test the remove_stop_words function
        with patch("nltk.corpus.stopwords.words", return_value=["a", "the"]):
            words_list = ["a", "quick", "brown", "fox"]
            expected = ["quick", "brown", "fox"]
            self.assertEqual(remove_stop_words(words_list), expected)

    def test_remove_stop_words_only_stopwords(self):
        """
        Tests remove_stop_words()
        """
        # Test with only stopwords
        with patch("nltk.corpus.stopwords.words", return_value=["a", "the"]):
            words_list = ["a", "the"]
            expected = []
            self.assertEqual(remove_stop_words(words_list), expected)

    def test_remove_stop_words_no_stopwords(self):
        """
        Tests remove_stop_words()
        """
        # Test with no stopwords
        with patch("nltk.corpus.stopwords.words", return_value=["a", "the"]):
            words_list = ["quick", "brown", "fox"]
            expected = ["quick", "brown", "fox"]
            self.assertEqual(remove_stop_words(words_list), expected)

    def test_lemmatize(self):
        """
        Tests lemmatize()
        """
        # Test the lemmatize function
        with patch("nltk.stem.WordNetLemmatizer.lemmatize", side_effect=lambda x: x + "_lemmatized"):
            words_list = ["running", "jumps"]
            expected = ["running_lemmatized", "jumps_lemmatized"]
            self.assertEqual(lemmatize(words_list), expected)
