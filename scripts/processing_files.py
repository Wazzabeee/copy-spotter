import re
import zipfile
import slate3k as slate
from odf import text, teletype
from odf.opendocument import load
from os import path


def get_file_extension(filepath):
    """ Return the file extension of file at filepath """

    try:
        return path.splitext(filepath)[1]
    except:
        print("File extension error")
        return None


def file_extension_call(file):
    """ Map file extension to correct function call """

    extension = get_file_extension(file)

    if extension:
        if extension == '.pdf':
            return get_words_from_pdf_file(file)
        elif extension == '.docx':
            return get_words_from_docx_file(file)
        elif extension == '.odt':
            return get_words_from_odt_file(file)
        elif extension == '.txt':
            return get_words_from_txt_file(file)
        else:
            print("File format is not supported. Please convert to pdf, docx, odt or txt")
            return None

    return None


def get_words_from_pdf_file(pdf_path):
    """ Return list of words from pdf file """

    with open(pdf_path, 'rb') as f:
        extracted_text = slate.PDF(f)

    cleaned2 = re.sub('<(.|\n)*?>', '', str(extracted_text))
    return re.findall(r'\w+', cleaned2.lower())


def get_words_from_txt_file(txt_path):
    """ Return list of words from txt file """

    words = []

    with open(txt_path, encoding='utf-8') as f:

        for line in f:
            try:
                for word in line.split():
                    words.append(word.lower())
            except (UnicodeError, UnicodeDecodeError) as _:
                pass

    str_words = ' '.join(map(str, words))

    return re.findall(r'\w+', str_words)


def get_words_from_docx_file(docx_path):
    """ Return list of words from docx file """

    docx = zipfile.ZipFile(docx_path)
    content = docx.read('word/document.xml').decode('utf-8')
    cleaned2 = re.sub('<(.|\n)*?>', '', content)

    return re.findall(r'\w+', cleaned2.lower())


def get_words_from_odt_file(odt_path):
    """ Return list of words from odt file """

    textdoc = load(odt_path)
    allparas = textdoc.getElementsByType(text.P)

    full_text = str()

    for para in allparas:
        temp = teletype.extractText(para)
        full_text += temp.lower()

    return re.findall(r'\w+', full_text)
