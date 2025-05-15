#!/usr/bin/env python3
"""

    Copyright (C) 2020-2025 Miðeind ehf.

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


    Tests for the Yfirlestur web application.

"""

from typing import Dict, Any, List

import sys
import os

import pytest
from flask.testing import FlaskClient

# Hack to fix imports from parent directory
basepath, _ = os.path.split(os.path.realpath(__file__))
mainpath = os.path.join(basepath, "..")
if mainpath not in sys.path:
    sys.path.insert(0, mainpath)

from correct import check_grammar  # noqa
from correct import *  # noqa
from doc import *  # noqa
from main import app  # noqa
from main import *  # noqa
from nertokenizer import *  # noqa
from settings import *  # noqa

@pytest.fixture
def client() -> FlaskClient:
    """Instantiate Flask's modified Werkzeug client to use in tests"""
    app.config["TESTING"] = True
    app.config["DEBUG"] = True
    return app.test_client()


HTML_MIME_TYPE = "text/html"
JSON_MIME_TYPE = "application/json"


def test_html_page_routes(client: FlaskClient):
    """Test all page routes in web application."""
    for page in ["/", "/about"]:
        resp = client.get(page)
        assert resp.status_code == 200
        assert resp.content_type.startswith(HTML_MIME_TYPE)
        assert resp.content_length > 100


def verify_correct_api_response(resp):
    """Verify response from /correct.api sync route."""
    assert resp.status_code == 200
    assert resp.content_type.startswith(JSON_MIME_TYPE)
    assert resp.json and isinstance(resp.json, dict)
    assert resp.json["valid"]
    assert "result" in resp.json and isinstance(resp.json["result"], list)
    assert "stats" in resp.json and isinstance(resp.json["stats"], dict)
    assert "text" in resp.json and isinstance(resp.json["text"], str)


def post_correct_request(
    client: FlaskClient, text: str, opts: Dict = {}, json=False
) -> Any:
    payload = {"text": text}
    payload.update(opts)
    if json:
        return client.post("/correct.api", json=payload)
    else:
        return client.post("/correct.api", data=payload)


def test_api_sync_routes(client: FlaskClient):
    """Test synchronous API routes in web application."""
    sent = "Þetta er prufa."

    # www form url-encoded POST request
    resp = post_correct_request(client, sent, json=False)
    verify_correct_api_response(resp)

    # JSON POST request
    resp = post_correct_request(client, sent, json=True)
    verify_correct_api_response(resp)


def test_api_correct_sync_route_with_options(client: FlaskClient):
    """Test /correct.api options."""

    def verify_options(
        text: str, opts: Dict[str, Any], expected_num_ann=0, json=False
    ) -> None:
        resp = post_correct_request(client, text, opts, json=json)
        verify_correct_api_response(resp)
        assert resp.json  # Silence type checker
        assert len(resp.json["result"][0][0]["annotations"]) == expected_num_ann

    # Test annotate_unparsed_sentences option
    SENT1 = "Ég kannaði firðinum ásamt hún."  # Should not parse!
    # Verify no result when false
    verify_options(SENT1, {"annotate_unparsed_sentences": False}, expected_num_ann=0)
    # Verify one result when true
    verify_options(SENT1, {"annotate_unparsed_sentences": True}, expected_num_ann=1)
    # Verify that true is the default
    verify_options(SENT1, {}, expected_num_ann=1)

    # Test suppress_suggestions option
    SENT2 = "Það var gott að koma tímalega á áfangastað."  # tímalega -> tímanlega
    # Verify no result when true
    verify_options(SENT2, {"suppress_suggestions": True}, expected_num_ann=0)
    # Verify one result when false
    verify_options(SENT2, {"suppress_suggestions": False}, expected_num_ann=1)
    # Verify that false is the default
    verify_options(SENT2, {}, expected_num_ann=1)

    # Test ignore_wordlist
    SENT3 = "Það var flargor í gær."
    W2IGN = ["flargor"]
    # No annotations since "flargor" is ignored
    verify_options(SENT3, {"ignore_wordlist": W2IGN}, expected_num_ann=0, json=True)
    # Otherwise, one annotation
    verify_options(SENT3, {}, expected_num_ann=1, json=True)

    # Test ignore_rules
    SENT4 = "Mér langar í brauðsneið."
    R2IGN = ["P_WRONG_CASE_þgf_þf"]
    # No annotations since "P_WRONG_CASE_þgf_þf" rule is ignored
    verify_options(SENT4, {"ignore_rules": R2IGN}, expected_num_ann=0, json=True)
    # Otherwise, one annotation
    verify_options(SENT4, {}, expected_num_ann=1, json=True)


def test_api_async_routes(client: FlaskClient):
    """Test asynchronous API routes in web application."""

    # /correct.task
    resp = client.post("/correct.task", data={"text": "Þetta er prufa."})
    assert resp.status_code == 202  # Accepted
    assert resp.content_type.startswith(JSON_MIME_TYPE)
    assert isinstance(resp.json, dict)
    assert "progress" in resp.json and isinstance(resp.json["progress"], float)
    assert resp.headers["Location"].startswith("/status/")


def verify_char_spans(text: str, real: List[int]) -> None:
    resp = check_grammar(text)
    i = [i.get("i", 0) for i in resp[0][0][0]["tokens"]]  # t.original is in i["o"]
    # if real != i:
    #    print(text)
    #    print(f"Result: {i}")
    #    print(f"Real:   {real}")
    #    pprint(resp)
    # else:
    #    pprint(resp)
    assert real == i


def test_character_spans() -> None:

    # Only 'normal' tokens
    text = "Ég á hest."
    real = [0, 2, 4, 9]
    verify_char_spans(text, real)

    # Person token tests
    text = "Á Clinton."
    real = [0, 1, 9]
    verify_char_spans(text, real)

    text = "Charles Parkton."
    real = [0, 15]
    verify_char_spans(text, real)

    text = "Hér er Nanna."
    real = [0, 3, 6, 12]
    verify_char_spans(text, real)

    text = "Hér er Maríanna Gvendardóttir."
    real = [0, 3, 6, 29]
    verify_char_spans(text, real)

    # Entity tokens
    text = "Hér er von Óskar."
    real = [0, 3, 6, 10, 16]
    verify_char_spans(text, real)

    text = "Hér er Óskar von í dag."
    real = [0, 3, 6, 16, 16, 18, 22]  # First token retains the original text
    verify_char_spans(text, real)

    # MW compound tests
    text = "Ég er umhverfis- og auðlindaráðherra."
    real = [0, 2, 5, 36]
    verify_char_spans(text, real)

    text = "Við erum þingkonur og -menn."
    real = [0, 3, 8, 18, 21, 27]
    verify_char_spans(text, real)

    text = "Ég er umhverfis-og auðlindaráðherra."
    real = [0, 2, 5, 35]
    verify_char_spans(text, real)

    text = "Ég er katta -og hundakona."
    real = [0, 2, 5, 11, 15, 25]  # TODO Should be merged into one token
    verify_char_spans(text, real)

    # MWE tests
    text = "Ég á meðal annars hest."
    real = [0, 2, 4, 17, 22]
    verify_char_spans(text, real)

    text = "Ég borða með bestu list."
    real = [0, 2, 8, 12, 18, 23]
    verify_char_spans(text, real)

    # amount tests
    text = "Ég á 500 milljónir króna."
    real = [0, 2, 4, 24]
    verify_char_spans(text, real)

    # Deletion tests
    text = "Ég á á."
    real = [0, 2, 4, 6]  # No longer automatically deleted, only marked as a possible error
    verify_char_spans(text, real)

    text = (
        "Ég datt datt."  # Merged into one token, suggestion for deleting one
    )
    real = [0, 2, 12]
    verify_char_spans(text, real)

    # E-mail
    text = "Hér er valid@email.com í gangi."
    real = [0, 3, 6, 22, 24, 30]
    verify_char_spans(text, real)

    # Wrong compounds
    # af hverju -> 'af' retains the original token text,
    # 'hverju' has original set to empty
    text = "Ég veit afhverju fuglinn galar."
    real = [0, 2, 7, 16, 16, 24, 30]
    verify_char_spans(text, real)

    # Wrong formers
    text = "Ég á fjölnotapoka."
    real = [0, 2, 4, 17, 17]
    verify_char_spans(text, real)

    # Free morphemes
    text = "Ég er ofgamall."
    real = [0, 2, 5, 14, 14]
    verify_char_spans(text, real)

    text = "Ég er kvennhatari."
    real = [0, 2, 5, 17]
    verify_char_spans(text, real)

    # Split compounds
    text = "Hér er ein birni."
    real = [0, 3, 6, 16]
    verify_char_spans(text, real)

    # TODO: Fix these tests
    # Spelling errors
    # text = "Ég varð fyri bíl."
    # real = [0, 2, 7, 12, 16]
    # verify_char_spans(text, real)

    # Ambiguous phrases
    # text = "Ég varð afar stór."
    # real = [0, 2, 7, 12, 17]
    # verify_char_spans(text, real)


def test_doc():
    """Test document-related functions in doc.py"""
    from doc import PlainTextDocument, DocxDocument

    txt_bytes = "Halló, gaman að kynnast þér.\n\nHvernig gengur?".encode("utf-8")
    doc = PlainTextDocument(txt_bytes)
    assert doc.extract_text() == txt_bytes.decode("utf-8")

    # Change to same directory as this file in order
    # to resolve relative path to files used by tests
    prev_dir = os.getcwd()
    abspath = os.path.abspath(__file__)
    dname = os.path.dirname(abspath)
    os.chdir(dname)

    txt = "Þetta er prufa.\n\nLína 1.\n\nLína 2."
    doc = DocxDocument("files/test.docx")
    assert doc.extract_text() == txt

    # Change back to previous directory
    os.chdir(prev_dir)
