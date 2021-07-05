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

def checking(text, real):
    resp = check_grammar(text)
    i = list([ i["i"] for i in resp[0][0][0]['tokens'] ])
    assert real == i
    #if real != i:
    #    print(text)
    #    print(f"Result: {i}")
    #    print(f"Real:   {real}")
    #    pprint(resp)
    #else:
    #    pprint(resp)


def test_character_spans():

    # Person token tests
    text = "Á Clinton."
    real = [0, 1, 8]
    checking(text, real)

    text = "Charles Parkton."
    real = [0, 15]
    checking(text, real)
    
    text = "Hér er Nanna."
    real = [0, 3, 5, 10]
    checking(text, real)

    text = "Hér er Maríanna Gvendardóttir."
    real = [0, 3, 5, 27]
    checking(text, real)

    # Entity tokens
    text = "Hér er von Óskar."
    real = [0, 3, 5, 8, 13]
    checking(text, real)

    text = "Hér er Óskar von í dag."
    real = [0, 3, 5, 10, 13, 14, 17]
    checking(text, real)


    # MW compound tests
    text = "Ég er umhverfis- og auðlindaráðherra."
    real = [0, 2, 4, 34]
    checking(text, real)

    text = "Við erum þingkonur og -menn."
    real = [0, 3, 7, 16, 18, 23]
    checking(text, real)

    text = "Ég er umhverfis-og auðlindaráðherra."
    real = [0, 2, 4, 33]
    checking(text, real)

    text = "Ég er umhverfis-og auðlindaráðherra."
    real = [0, 2, 4, 33]            # TODO merkja þetta sem villu!
    checking(text, real)

    text = "Ég er katta -og hundakona."
    real = [0, 2, 4, 9, 12, 21]         # TODO Ekki sameinað í einn tóka!
    checking(text, real)

    # MWE tests
    text = "Ég á meðal annars hest."
    real = [0, 2, 3, 16, 20]
    checking(text, real)

    text = "Ég borða með bestu list."
    real = [0, 2, 7, 10, 15, 19]
    checking(text, real)

    # amount tests 
    text = "Ég á 500 milljónir króna."
    real = [0, 2, 3, 22]
    checking(text, real)

    # Deletion tests
    text = "Ég á á."
    real = [0, 2, 3, 4]     # Ekki tekið sjálfkrafa út, bara merkt sem möguleg villa
    checking(text, real)

    text = "Ég datt datt."  # Núna sameinað í einn tóka og stungið upp á að taka annan út
    real = [0, 2, 11]
    checking(text, real)

    # E-mail
    text = "Hér er valid@email.com í gangi."
    real = [0, 3, 5, 20, 21, 26]
    checking(text, real)


    # Wrong compounds
    text = "Ég veit afhverju fuglinn galar."
    real = [0, 2, 6, 8, 14, 21, 26]     # TODO eða halda sem einum tóka og skipta upp þar? En það hefur áhrif á þáttun.
    checking(text, real)

    # Wrong formers
    text = "Ég á fjölnotapoka."
    real = [0, 2, 3, 11, 15]
    checking(text, real)

    # Free morphemes
    text = "Ég er ofgamall."
    real = [0, 2, 4, 6, 12]
    checking(text, real)

    text = "Ég er kvennhatari."
    real = [0, 2, 4, 15]
    checking(text, real)
    

    # Split compounds
    text = "Hér er ein birni."
    real = [0, 3, 5, 14]
    checking(text, real)

    # Spelling errors
    text = "Ég varð fyri bíl."
    real = [0, 2, 6, 10, 13]
    checking(text, real)

    # Ambiguous phrases
    text = "Ég varð afar stór."
    real = [0, 2, 6, 10, 14]
    checking(text, real)
    




