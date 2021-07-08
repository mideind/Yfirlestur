"""

    Greynir: Natural language processing for Icelandic

    High-level wrappers for checking grammar and spelling

    Copyright (C) 2021 Miðeind ehf.

    This software is licensed under the MIT License:

        Permission is hereby granted, free of charge, to any person
        obtaining a copy of this software and associated documentation
        files (the "Software"), to deal in the Software without restriction,
        including without limitation the rights to use, copy, modify, merge,
        publish, distribute, sublicense, and/or sell copies of the Software,
        and to permit persons to whom the Software is furnished to do so,
        subject to the following conditions:

        The above copyright notice and this permission notice shall be
        included in all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
        EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
        MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
        IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
        CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
        TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
        SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


    This module exports check_grammar(), a function called from main.py
    to apply grammar and spelling annotations to user-supplied text.

"""

from typing import (
    List,
    Tuple,
    Iterator,
    Iterable,
    Optional,
    Callable,
    cast,
)
from typing_extensions import TypedDict

import hashlib
import random

from reynir.bintokenizer import Tok, StringIterable
from reynir import Sentence

import reynir_correct
import nertokenizer
from reynir_correct.annotation import Annotation

# Salt that is used during generation of a hashed token
# to be returned when giving feedback on an annotation
START_SALT = "*[GC start]*"
END_SALT = "*[GC end]*"

# Type definitions

class StatsDict(TypedDict):

    """ Statistics returned from an annotation task """

    num_tokens: int
    num_sentences: int
    num_parsed: int
    num_chars: int
    ambiguity: float


class AnnDict(TypedDict):

    """ A single annotation, as returned by the API """

    start: int
    end: int
    start_char: int
    end_char: int
    code: str
    text: str
    detail: Optional[str]
    suggest: Optional[str]


class AnnTokenDict(TypedDict, total=False):

    """ Type of the token dictionaries returned from check_grammar() """

    # Token kind
    k: int
    # Token text
    x: str
    # Original text of token
    o: str
    # Character offset of token, indexed from the start of the checked text
    i: int


class AnnResultDict(TypedDict):

    """ The annotation result for a sentence """

    original: str
    tokens: List[AnnTokenDict]
    token: str
    nonce: str
    annotations: List[AnnDict]
    corrected: str


# List of sentences, each having an associated list of AnnResultDict instances
CheckResult = Tuple[List[List[AnnResultDict]], StatsDict]


class RecognitionPipeline(reynir_correct.CorrectionPipeline):

    """ Derived class that adds a named entity recognition pass
        to the GreynirCorrect tokenization pipeline """

    def __init__(self, text: StringIterable) -> None:
        super().__init__(text)

    def recognize_entities(self, stream: Iterator[Tok]) -> Iterator[Tok]:
        """ Recognize named entities using the nertokenizer module,
            but construct tokens using the Correct_TOK class from
            reynir_correct """
        return nertokenizer.recognize_entities(
            stream, token_ctor=reynir_correct.Correct_TOK
        )


class NERCorrect(reynir_correct.GreynirCorrect):

    """ Derived class to override the default tokenization of
        GreynirCorrect to perform named entity recognition """

    def __init__(self) -> None:
        super().__init__()

    def tokenize(self, text: StringIterable) -> Iterator[Tok]:
        """ Use the recognizing & correcting tokenizer instead
            of the normal one """
        pipeline = RecognitionPipeline(text)
        return pipeline.tokenize()


def generate_nonce() -> str:
    """ Generate a random nonce, consisting of 8 digits """
    return "{0:08}".format(random.randint(0, 10 ** 8 - 1))


def generate_token(original: str, nonce: str) -> str:
    """ Generate a 64-character token string using the original
        sentence string and the given nonce """
    return hashlib.sha256(
        (START_SALT + nonce + original + END_SALT).encode("utf-8")
    ).hexdigest()[:64]


def validate_token_and_nonce(original: str, token: str, nonce: str) -> bool:
    """ Check whether a given token/nonce combination corresponds to
        the original sentence given """
    return generate_token(original, nonce) == token


def check_grammar(
    text: str,
    *,
    progress_func: Optional[Callable[[float], None]] = None,
    split_paragraphs: bool = True,
) -> CheckResult:
    """ Check the grammar and spelling of the given text and return
        a list of annotated paragraphs, containing sentences, containing
        tokens. The progress_func, if given, will be called periodically
        during processing to indicate progress, with a ratio parameter
        which is a float in the range 0.0..1.0. """

    result = reynir_correct.check_with_custom_parser(
        text,
        split_paragraphs=split_paragraphs,
        parser_class=NERCorrect,
        progress_func=progress_func,
    )

    # Character index of each token within the submitted text,
    # counting from its beginning
    offset = 0

    def encode_sentence(sent: Sentence) -> AnnResultDict:
        """ Map a reynir._Sentence object to a raw sentence dictionary
            expected by the web UI """
        tokens: List[AnnTokenDict]
        if sent.tree is None:
            # Not parsed: use the raw token list
            tokens = [
                AnnTokenDict(k=d.kind, x=d.txt, o=d.original or d.txt)
                for d in sent.tokens
            ]
        else:
            # Successfully parsed: use the text from the terminals (where available)
            # since we have more info there, for instance on em/en dashes.
            # Create a map of token indices to corresponding terminal text
            assert sent.terminals is not None
            token_map = {t.index: t.text for t in sent.terminals}
            tokens = [
                AnnTokenDict(
                    k=d.kind, x=token_map.get(ix, d.txt), o=d.original or d.txt
                )
                for ix, d in enumerate(sent.tokens)
            ]
        # Add token character offsets to the annotation tokens
        nonlocal offset
        for ix, t in enumerate(sent.tokens):
            tokens[ix]["i"] = offset
            offset += len(t.original or "")
        a: Iterable[Annotation] = getattr(
            sent, "annotations", cast(List[Annotation], [])
        )
        len_tokens = len(tokens)
        # Reassemble the original sentence text, as the tokenizer saw it
        original = "".join((t.original or "") for t in sent.tokens)
        # Create a nonce and a token that the user must return correctly
        # to give feedback on this annotation via the /feedback endpoint
        nonce = generate_nonce()
        token = generate_token(original, nonce)
        annotations: List[AnnDict] = [
            AnnDict(
                # Start token index of this annotation
                start=ann.start,
                # End token index (inclusive)
                end=ann.end,
                # Character offset of the start of the annotation in the original text
                start_char=tokens[ann.start].get("i", 0),
                # Character offset of the end of the annotation in the original text
                # (inclusive, i.e. the offset of the last character)
                end_char=(
                    tokens[ann.end + 1].get("i", 0)
                    if ann.end + 1 < len_tokens
                    else offset
                ) - 1,
                code=ann.code,
                text=ann.text,
                detail=ann.detail,
                suggest=ann.suggest,
            )
            for ann in a
        ]
        return AnnResultDict(
            original=original,
            tokens=tokens,
            token=token,
            nonce=nonce,
            annotations=annotations,
            corrected=sent.tidy_text,
        )

    pglist = result["paragraphs"]
    pgs = [[encode_sentence(sent) for sent in pg] for pg in pglist]

    stats = StatsDict(
        num_tokens=result["num_tokens"],
        num_sentences=result["num_sentences"],
        num_parsed=result["num_parsed"],
        num_chars=offset,
        ambiguity=result["ambiguity"],
    )

    return pgs, stats
