""" This module is used to process text in docx, odt, txt and pdf files """

import re
import zipfile
from os import path

import pdfplumber
import slate3k as slate
from odf import text, teletype
from odf.opendocument import load


def get_file_extension(filepath: str) -> str:
    """Return the file extension of the file at the specified path"""
    if not path.isfile(filepath):
        print("Invalid file path")
        return ""

    try:
        return path.splitext(filepath)[1]
    except IndexError:
        print("File extension error")
        return ""


def file_extension_call(file: str) -> list:
    """Map file extension to appropriate function"""

    extension = get_file_extension(file)

    if extension:
        if extension == ".pdf":
            return get_words_from_pdf_file(file)
        if extension == ".docx":
            return get_words_from_docx_file(file)
        if extension == ".odt":
            return get_words_from_odt_file(file)
        if extension == ".txt":
            return get_words_from_txt_file(file)

    print("File format is not supported. Please convert to pdf, docx, odt or txt")
    return []


def get_words_from_pdf_file(pdf_path: str) -> list:
    """Return list of words from pdf file at specified path"""

    with open(pdf_path, "rb") as file:
        extracted_text = slate.PDF(file)

    nested_lists_length_sum = sum(len(temp) for temp in extracted_text)
    count_line_return = sum(string.count("\n") for string in extracted_text)

    # Check \n ratio compared to length of text
    if nested_lists_length_sum / count_line_return > 10:
        for i, _ in enumerate(extracted_text):
            extracted_text[i] = extracted_text[i].replace("\n", " ")
            extracted_text[i] = re.sub("<(.|\n)*?>", "", str(extracted_text[i]))
            extracted_text[i] = re.findall(r"\w+", extracted_text[i].lower())

        return [item for sublist in extracted_text for item in sublist]

    # Pdf format is not readable by Slate library
    return get_words_from_special_pdf(pdf_path)


def get_words_from_special_pdf(pdf_path: str) -> list:
    """Return list of words from a PDF file when the Slate library can't scrape it"""

    with pdfplumber.open(pdf_path) as file:
        concat_string = ""
        for page in file.pages:
            text_page = page.extract_text() + "\n"
            concat_string += text_page

    # Split the string into words and return as a list
    return concat_string.replace("\xa0", " ").strip().split()


def get_words_from_txt_file(txt_path: str) -> list:
    """Return list of words from txt file at specified path"""

    words = []

    with open(txt_path, encoding="utf-8") as file:
        for line in file:
            try:
                for word in line.split():
                    words.append(word.lower())
            except (UnicodeError, UnicodeDecodeError):
                pass

    str_words = " ".join(map(str, words))

    return re.findall(r"\w+", str_words)


def get_words_from_docx_file(docx_path: str) -> list:
    """Return list of words from docx file at specified path"""

    with zipfile.ZipFile(docx_path) as docx:
        content = docx.read("word/document.xml").decode("utf-8")
        cleaned = re.sub("<(.|\n)*?>", "", content)

    return re.findall(r"\w+", cleaned.lower())


def get_words_from_odt_file(odt_path: str) -> list:
    """Return list of words from odt file at specified path"""

    textdoc = load(odt_path)
    paragraphs = textdoc.getElementsByType(text.P)

    full_text = str()

    for paragraph in paragraphs:
        temp = teletype.extractText(paragraph)
        full_text += temp.lower()

    return re.findall(r"\w+", full_text)
