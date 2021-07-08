#!/usr/bin/env python3
"""

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


"""

import sys
import os

# Hack to fix imports from parent directory
basepath, _ = os.path.split(os.path.realpath(__file__))
mainpath = os.path.join(basepath, "..")
if mainpath not in sys.path:
    sys.path.insert(0, mainpath)


from correct import *  # noqa
from doc import *  # noqa
from main import *  # noqa
from nertokenizer import *  # noqa
from settings import *  # noqa

# from pprint import pprint

def checking(text: str, real: List[int]) -> None:
    resp = check_grammar(text)
    i = [ i["i"] for i in resp[0][0][0]['tokens'] ] # t.original is in i["o"]
    #if real != i:
    #    print(text)
    #    print(f"Result: {i}")
    #    print(f"Real:   {real}")
    #    pprint(resp)
    #else:
    #    pprint(resp)
    assert real == i


def test_character_spans() -> None:

    # Only 'normal' tokens
    text = "Ég á hest."
    real = [0, 2, 4, 9]
    checking(text, real)

    # Person token tests
    text = "Á Clinton."
    real = [0, 1, 9]
    checking(text, real)

    text = "Charles Parkton."
    real = [0, 15]
    checking(text, real)
    
    text = "Hér er Nanna."
    real = [0, 3, 6, 12]
    checking(text, real)

    text = "Hér er Maríanna Gvendardóttir."
    real = [0, 3, 6, 29]
    checking(text, real)

    # Entity tokens
    text = "Hér er von Óskar."
    real = [0, 3, 6, 10, 16]
    checking(text, real)

    text = "Hér er Óskar von í dag."
    real = [0, 3, 6, 16, 16, 18, 22]        # First token retains the original text
    checking(text, real)

    # MW compound tests
    text = "Ég er umhverfis- og auðlindaráðherra."
    real = [0, 2, 5, 36]
    checking(text, real)

    text = "Við erum þingkonur og -menn."
    real = [0, 3, 8, 18, 21, 27]
    checking(text, real)

    text = "Ég er umhverfis-og auðlindaráðherra."
    real = [0, 2, 5, 35]
    checking(text, real)

    text = "Ég er katta -og hundakona."
    real = [0, 2, 5, 11, 15, 25]         # TODO Ekki sameinað í einn tóka!
    checking(text, real)

    # MWE tests
    text = "Ég á meðal annars hest."
    real = [0, 2, 4, 17, 22]
    checking(text, real)

    text = "Ég borða með bestu list."
    real = [0, 2, 8, 12, 18, 23]
    checking(text, real)

    # amount tests 
    text = "Ég á 500 milljónir króna."
    real = [0, 2, 4, 24]
    checking(text, real)

    # Deletion tests
    text = "Ég á á."
    real = [0, 2, 4, 6]     # Ekki lengur tekið sjálfkrafa út, bara merkt sem möguleg villa
    checking(text, real)

    text = "Ég datt datt."  # Núna sameinað í einn tóka og stungið upp á að taka annan út
    real = [0, 2, 12]
    checking(text, real)

    # E-mail
    text = "Hér er valid@email.com í gangi."
    real = [0, 3, 6, 22, 24, 30]
    checking(text, real)

    # Wrong compounds
    # af hverju -> 'af' retains the original token text,
    # 'hverju' has original set to empty
    text = "Ég veit afhverju fuglinn galar."
    real = [0, 2, 7, 16, 16, 24, 30]
    checking(text, real)

    # Wrong formers
    text = "Ég á fjölnotapoka."
    real = [0, 2, 4, 17, 17]
    checking(text, real)

    # Free morphemes
    text = "Ég er ofgamall."
    real = [0, 2, 5, 14, 14]
    checking(text, real)

    text = "Ég er kvennhatari."
    real = [0, 2, 5, 17]
    checking(text, real)
    
    # Split compounds
    text = "Hér er ein birni."
    real = [0, 3, 6, 16]
    checking(text, real)

    # Spelling errors
    text = "Ég varð fyri bíl."
    real = [0, 2, 7, 12, 16]
    checking(text, real)

    # Ambiguous phrases
    text = "Ég varð afar stór."
    real = [0, 2, 7, 12, 17]
    checking(text, real)



