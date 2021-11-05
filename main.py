import re
import sys
import zipfile
import difflib
from tabulate import tabulate
from os import path, listdir
import webbrowser

import slate3k as slate
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from odf import text, teletype
from odf.opendocument import load


# TODO Implement Cosine Similarity


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


def remove_numbers(words_list):
    """ Remove all numbers from strings list to avoid errors later """

    temp = [w for w in words_list if not isinstance(w, int)]
    return [w for w in temp if not isinstance(w, float)]


def remove_stop_words(words_list):
    """ Remove stop words from strings list """

    stop_words = set(stopwords.words('english'))

    return [w for w in words_list if str(w).lower not in stop_words]


def lemmatize(words_list):
    """ return lemmatized words list """

    lemmatizer = WordNetLemmatizer()

    return [lemmatizer.lemmatize(w) for w in words_list]


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


def pretty_table(scores, names):
    """ Print similarity results nicely """

    row_format = "{:>15}" * (len(names) + 1)
    print(row_format.format("", *names))
    for name, row in zip(names, scores):
        print(row_format.format(name, *row))


def difflib_overlap(word_token1, word_token2):
    """ Get similarity percentage from matching sequences between two strings """

    matching_blocks = difflib.SequenceMatcher(a=word_token1, b=word_token2).get_matching_blocks()
    len_sum = sum([len(block) for block in matching_blocks])

    seq = difflib.SequenceMatcher(a=word_token1, b=word_token2)

    for match in difflib.SequenceMatcher(a=word_token1, b=word_token2).get_matching_blocks():
        print("Match             : {}".format(match))
        print("Matching Sequence : {}".format(word_token1[match.a:match.a + match.size]))

    return round(seq.ratio() * 100, 3)


def calculate_overlap(word_token1, word_token2):
    """ Get similirity percentage from usqge of similar words in two strings """

    overlapping_words = []

    for w in word_token1:
        if w in word_token2:
            overlapping_words.append(w)

    overlap_percentage = len(overlapping_words)/len(word_token1)*100

    return round(overlap_percentage, 3)


def calculate_jaccard(word_tokens1, word_tokens2):
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


def results_to_html(scores, filenames):

    for ind in range(len(filenames)):
        scores[ind].insert(0, filenames[ind])

    scores.insert(0, filenames)
    scores[0].insert(0, '')

    with open('results.html', 'w') as f:
        f.write(tabulate(scores, tablefmt='html'))


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
                        processed_files.append(file_extension_call(student_papers + '\\' + filename))
                        filenames.append(filename)

                jaccard_scores = [[] for _ in range(len(processed_files))]
                overlap_scores = [[] for _ in range(len(processed_files))]
                difflib_scores = [[] for _ in range(len(processed_files))]

                for i, text in enumerate(processed_files):
                    for j, text_bis in enumerate(processed_files):
                        if i != j:
                            jaccard_scores[i].append(calculate_jaccard(text, text_bis))
                            overlap_scores[i].append(calculate_overlap(text, text_bis))
                            difflib_scores[i].append(difflib_overlap(text, text_bis))
                        else:
                            jaccard_scores[i].append(-1)
                            overlap_scores[i].append(-1)
                            difflib_scores[i].append(-1)

                print("\n \n Jaccard similarity \n")
                pretty_table(jaccard_scores, filenames)
                print("\n \n Percentage of overlapping \n")
                pretty_table(overlap_scores, filenames)
                print("\n \n Percentage of mathcing sequences from difflib \n")
                pretty_table(difflib_scores, filenames)
                results_to_html(difflib_scores, filenames)
                webbrowser.open(r'C:\Users\Clément\Documents\GitHub\pythonProject\results.html')
        else:
            print("Check main paper format")
            exit()

    else:
        p1 = "C:\\Users\\Clément\\Downloads\\real_student_reports\\students\\p6.docx"
        p2 = "C:\\Users\\Clément\\Downloads\\real_student_reports\\students\\p7.pdf"

        s1 = file_extension_call(p1)
        s2 = file_extension_call(p2)
        print(len(s1))
        print(len(s2))
        print(difflib_overlap(s1, s2))
        print(difflib_overlap(s2, s1))
        results_to_html('a','b')
        print("Missing mandatory parameters")
        print("python script.py  full_path_to_student_files_directory full_path_to_reference_file ")
