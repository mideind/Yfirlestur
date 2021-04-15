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
    Dict,
    Tuple,
    Any,
    Union,
    Iterator,
    Iterable,
    Optional,
    Callable,
    cast,
)

from reynir.bintokenizer import Tok, StringIterable
from reynir import Sentence, Paragraph

import reynir_correct
import nertokenizer
from reynir_correct.annotation import Annotation


# Type definitions
StatsDict = Dict[str, Union[int, float]]


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


def check_grammar(
    text: str, *, progress_func: Optional[Callable[[float], None]] = None
) -> Tuple[Any, StatsDict]:
    """ Check the grammar and spelling of the given text and return
        a list of annotated paragraphs, containing sentences, containing
        tokens. The progress_func, if given, will be called periodically
        during processing to indicate progress, with a ratio parameter
        which is a float in the range 0.0..1.0. """

    result = reynir_correct.check_with_custom_parser(
        text,
        split_paragraphs=True,
        parser_class=NERCorrect,
        progress_func=progress_func,
    )

    def encode_sentence(sent: Sentence) -> Dict[str, Any]:
        """ Map a reynir._Sentence object to a raw sentence dictionary
            expected by the web UI """
        tokens: List[Dict[str, Union[int, str]]]
        if sent.tree is None:
            # Not parsed: use the raw token list
            tokens = [dict(k=d.kind, x=d.txt) for d in sent.tokens]
        else:
            # Successfully parsed: use the text from the terminals (where available)
            # since we have more info there, for instance on em/en dashes.
            # Create a map of token indices to corresponding terminal text
            assert sent.terminals is not None
            token_map = {t.index: t.text for t in sent.terminals}
            tokens = [
                dict(k=d.kind, x=token_map.get(ix, d.txt))
                for ix, d in enumerate(sent.tokens)
            ]
        a = cast(Iterable[Annotation], getattr(sent, "annotations", []))
        annotations: List[Dict[str, Any]] = [
            dict(
                start=ann.start,
                end=ann.end,
                code=ann.code,
                text=ann.text,
                detail=ann.detail,
                suggest=ann.suggest,
            )
            for ann in a
        ]
        return dict(tokens=tokens, annotations=annotations, corrected=sent.tidy_text,)

    pglist = cast(Iterable[Paragraph], result["paragraphs"])
    pgs = [[encode_sentence(sent) for sent in pg] for pg in pglist]

    stats: StatsDict = dict(
        num_tokens=cast(int, result["num_tokens"]),
        num_sentences=cast(int, result["num_sentences"]),
        num_parsed=cast(int, result["num_parsed"]),
        ambiguity=cast(float, result["ambiguity"]),
    )

    return pgs, stats
