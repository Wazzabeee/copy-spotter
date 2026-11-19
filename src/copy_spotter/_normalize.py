"""Optional normalization of the words that are matched: accents folded, stopwords left out.

Normalization works on the words of a document, never on its text: the display text and the character span of
every remaining word are kept, so reports still highlight the original text.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import replace
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:
    from copy_spotter._documents import Document

Normalization = Literal["accents"]
"""``accents``: fold accents and compatibility characters, so "élève" matches "eleve" and "ﬁnal" matches "final"."""

NORMALIZATIONS: tuple[Normalization, ...] = get_args(Normalization)

# Common function words (articles, pronouns, prepositions, conjunctions, auxiliaries), lowercase, written with
# their accents. Each language is one space-separated string to keep the lists compact and easy to review.
_STOPWORDS = {
    "en": """
        a about above after again against all am an and any are as at be because been before being below between
        both but by can could did do does doing down during each few for from further had has have having he her
        here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not
        now of off on once only or other our ours ourselves out over own same she should so some such than that the
        their theirs them themselves then there these they this those through to too under until up very was we
        were what when where which while who whom why will with would you your yours yourself yourselves
    """,
    "fr": """
        a à afin ai aie aient aies ait as au aucun aussi autre aux avaient avais avait avec avez aviez avions avoir
        avons ayant c ce ceci cela celle celles celui ces cet cette ceux chaque comme d dans de des donc dont du
        elle elles en entre es est et été étaient étais était être eu eux fait il ils j je l la le les leur leurs
        lui m ma mais me même mes moi mon n ne ni nos notre nous on ont ou où par pas pendant peu peut plus pour
        qu que quel quelle quelles quels qui s sa sans se sera seront ses si son sont sous sur t ta te tes toi ton
        tous tout toute toutes très tu un une vos votre vous y
    """,
    "es": """
        a al algo algunas algunos ante antes como con contra cual cuando de del desde donde durante e el él ella
        ellas ellos en entre era erais eran eras eres es esa esas ese eso esos esta está estaba estaban estado
        están estar estas este esto estos fue fueron fui ha había habían han has hasta hay la las le les lo los
        más me mi mis mucho muy nada ni no nos nosotros o os otra otras otro otros para pero poco por porque que
        qué quien se sea ser si sí sido sin sobre son su sus también tanto te tiene tienen todo todos tu tus un
        una uno unos vosotros y ya yo
    """,
    "de": """
        aber alle allem allen aller alles als also am an ander andere anderen auch auf aus bei bin bis bist da
        damit dann das dass dem den denn der des dich die dies diese diesem diesen dieser dieses dir doch dort du
        durch ein eine einem einen einer eines er es etwas euch euer für gegen hab habe haben hat hatte hatten
        hier hin ich ihm ihn ihnen ihr ihre ihrem ihren ihrer im in ins ist ja jede jedem jeden jeder jedes jetzt
        kann kein keine können man manche mein meine mich mir mit muss nach nicht nichts noch nun nur ob oder ohne
        sehr sein seine seinem seinen seiner sich sie sind so solche soll sollte sondern über um und uns unser
        unter viel vom von vor war waren warst was weil welche welchem welchen welcher wenn wer werden wie wieder
        will wir wird wo wollen würde zu zum zur zwar zwischen
    """,
    "it": """
        a ad agli ai al alla alle allo anche avere aveva c che chi ci come con contro cui da dal dalla dalle dei
        del della delle dello di dove e è ed era erano essere gli ha hanno ho i il in io la le lei li lo loro lui
        ma mi mia mie miei mio ne negli nei nel nella nelle no noi non nostra nostro o per perché più quale quando
        quella quelle quello questa queste questi questo se sei si sia siamo sono sopra sotto sta stato su sua
        sue sui sul sulla suo suoi tra tu tutti tutto un una uno voi
    """,
    "pt": """
        a à ao aos as às até com como da das de dela dele deles do dos e é ela elas ele eles em entre era eram
        essa essas esse esses esta está estão estas este estes eu foi foram há isso isto já lhe lhes mais mas me
        mesmo meu minha muito na nas não nem no nos nós nossa nosso num numa o os ou para pela pelas pelo pelos
        por porque quando que quem se sem ser seu seus só sua suas também te tem têm tu tua um uma você vocês
    """,
}

STOPWORD_LANGUAGES: tuple[str, ...] = tuple(_STOPWORDS)


def stopword_list(*languages: str) -> frozenset[str]:
    """Return the built-in stopwords of one or more languages, lowercase and with their accents.

    Args:
        languages: Codes from :data:`STOPWORD_LANGUAGES`: ``"en"``, ``"fr"``, ``"es"``, ``"de"``, ``"it"``,
            ``"pt"`` (case-insensitive).

    Raises:
        ValueError: A language has no built-in list.
    """
    words: set[str] = set()
    for language in languages:
        code = language.strip().lower()
        if code not in _STOPWORDS:
            raise ValueError(f"no stopword list for {language!r}; available: {', '.join(STOPWORD_LANGUAGES)}")
        words.update(_STOPWORDS[code].split())
    return frozenset(words)


def check_normalize(normalize: Iterable[str]) -> tuple[Normalization, ...]:
    """Return the normalizations without duplicates, in :data:`NORMALIZATIONS` order, or raise ``ValueError``."""
    requested = set(normalize)
    unknown = sorted(requested.difference(NORMALIZATIONS))
    if unknown:
        raise ValueError(f"normalize must be among {', '.join(NORMALIZATIONS)}, got {', '.join(map(repr, unknown))}")
    return tuple(n for n in NORMALIZATIONS if n in requested)


def fold_accents(word: str) -> str:
    """Return ``word`` without diacritics, with compatibility characters (ligatures, superscripts) decomposed."""
    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def normalize_document(document: Document, *, accents: bool, stopwords: frozenset[str]) -> Document:
    """Return ``document`` with its words normalized, and the stopwords removed from its words and spans.

    The display text is unchanged. Stopwords are compared after the same accent folding as the words, and a
    passage that differs only by its stopwords then matches as one block, highlighted from its first to its last
    word.
    """
    if not accents and not stopwords:
        return document
    if accents:
        stopwords = frozenset(fold_accents(word) for word in stopwords)
    words: list[str] = []
    spans: list[tuple[int, int]] = []
    for word, span in zip(document.words, document.spans, strict=True):
        key = fold_accents(word) if accents else word
        if key not in stopwords:
            words.append(key)
            spans.append(span)
    return replace(document, words=tuple(words), spans=tuple(spans))
