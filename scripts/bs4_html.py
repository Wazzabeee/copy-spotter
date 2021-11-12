from bs4 import BeautifulSoup as Bs
import os
from utils import is_float


def add_links_to_html_table(path: str) -> None:
    """ """

    html = open(path)
    soup = Bs(html, 'html.parser')
    file_ind = 0

    for td in soup.findAll('td'):

        if is_float(td.text):  # if td is not filename or -1

            tmp = soup.new_tag('a',
                               href='file:///' + path.replace('_results', str(file_ind)),
                               target="_blank")

            td.string.wrap(tmp)  # we wrap the td string between the hyperlink
            file_ind += 1

    with open(path, 'wb') as f_output:
        f_output.write(soup.prettify("utf-8"))
        f_output.flush()
        os.fsync(f_output.fileno())
        f_output.close()

    html.flush()
    html.close()
