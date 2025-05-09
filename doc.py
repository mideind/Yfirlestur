"""

    Yfirlestur: Online spelling and grammar correction for Icelandic

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

    This module contains code to extract text from documents
    such as plain text, html, rtf, pdf, odt, and docx files.

"""

from typing import Callable, List, Union, Dict, Type, Mapping, Any, cast

import re
import abc
from io import BytesIO, StringIO
from zipfile import ZipFile

from html2text import HTML2Text

from striprtf.striprtf import rtf_to_text  # type: ignore

from odf import teletype  # type: ignore
from odf import text as odf_text  # type: ignore
from odf.opendocument import load as load_odf  # type: ignore

from pdfminer.converter import TextConverter  # type: ignore
from pdfminer.layout import LAParams  # type: ignore
from pdfminer.pdfdocument import PDFDocument as PDFMinerDocument  # type: ignore
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter  # type: ignore
from pdfminer.pdfpage import PDFPage  # type: ignore
from pdfminer.pdfparser import PDFParser  # type: ignore

# Use defusedxml module to prevent parsing of malicious XML
from defusedxml import ElementTree  # type: ignore


DEFAULT_TEXT_ENCODING = "UTF-8"


DocumentType = Type["Document"]


class MalformedDocumentError(Exception):
    pass


class Document(abc.ABC):
    """Abstract base class for documents."""

    def __init__(self, path_or_bytes: Union[str, bytes]) -> None:
        """Accepts either a file path or bytes object"""
        if isinstance(path_or_bytes, str):
            # It's a file path
            with open(path_or_bytes, "rb") as file:
                self.data = file.read()
        else:
            # It's a byte stream
            self.data = path_or_bytes

    @staticmethod
    def for_mimetype(mime_type: str) -> DocumentType:
        return doc_class_for_mime_type(mime_type)

    @staticmethod
    def for_suffix(suffix: str) -> DocumentType:
        return doc_class_for_suffix(suffix)

    @abc.abstractmethod
    def extract_text(self) -> str:
        """All subclasses must implement this method."""
        raise NotImplementedError

    def write_to_file(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.data)


class PlainTextDocument(Document):
    """Plain text document."""

    def extract_text(self) -> str:
        return self.data.decode(DEFAULT_TEXT_ENCODING)


class HTMLDocument(Document):
    """HTML document."""

    @staticmethod
    def _remove_header_prefixes(text: str) -> str:
        """Removes '#' in all lines starting with '#'. Annoyingly,
        html2text adds markdown-style headers for <h*> tags."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("#"):
                lines[i] = re.sub(r"[#]+\s", "", line)
        return "\n".join(lines)

    def extract_text(self) -> str:
        html = self.data.decode(DEFAULT_TEXT_ENCODING)

        h = HTML2Text()
        # See https://github.com/Alir3z4/html2text/blob/master/html2text/cli.py
        h.ignore_links = True
        h.ignore_emphasis = True
        h.ignore_images = True
        h.unicode_snob = True
        h.ignore_tables = True
        h.decode_errors = "ignore"  # type: ignore
        h.body_width = 0

        txt = h.handle(html)

        return self._remove_header_prefixes(txt)


class RTFDocument(Document):
    """Rich text document."""

    def extract_text(self) -> str:
        txt = self.data.decode(DEFAULT_TEXT_ENCODING)

        # Hack to handle Apple's extensions to the RTF format
        txt = txt.replace("\\\n\\\n", "\\\n\\par\n")

        return cast(Callable[[str], str], rtf_to_text)(txt)


class PDFDocument(Document):
    """Adobe PDF document."""

    def extract_text(self) -> str:
        output_string = StringIO()

        parser = PDFParser(BytesIO(self.data))
        doc = PDFMinerDocument(parser)
        rsrcmgr = PDFResourceManager()
        device = TextConverter(rsrcmgr, output_string, laparams=LAParams())
        interpreter = PDFPageInterpreter(rsrcmgr, device)

        for page in PDFPage.create_pages(doc):  # type: ignore
            interpreter.process_page(page)  # type: ignore

        # Postprocessing
        txt = output_string.getvalue()
        txt = txt.replace("\n", " ")
        return txt


class DocxDocument(Document):
    """Microsoft docx document."""

    DOCXML_PATH = "word/document.xml"
    WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    PARAGRAPH_TAG = WORD_NAMESPACE + "p"
    TEXT_TAG = WORD_NAMESPACE + "t"
    BREAK_TAG = WORD_NAMESPACE + "br"

    def extract_text(self) -> str:
        zipfile = ZipFile(BytesIO(self.data), "r")

        # Verify that archive contains document.xml
        if self.DOCXML_PATH not in zipfile.namelist():
            raise MalformedDocumentError("Malformed docx file")

        # Read xml file from archive
        content = zipfile.read(self.DOCXML_PATH)
        zipfile.close()

        # Parse it
        tree: Any = ElementTree.fromstring(content)  # type: ignore

        # Extract text elements from all paragraphs
        # (with special handling of line breaks)
        paragraphs: List[str] = []
        p: Any
        for p in tree.iter(self.PARAGRAPH_TAG):
            texts: List[str] = []
            for node in p.iter():
                if node.tag.endswith(self.TEXT_TAG) and node.text:
                    texts.append(node.text)
                elif node.tag.endswith(self.BREAK_TAG):
                    texts.append("\n")
            if texts:
                paragraphs.append("".join(texts))

        return "\n\n".join(paragraphs)


class ODTDocument(Document):
    """OpenDocument format."""

    def extract_text(self) -> str:
        textdoc = load_odf(BytesIO(self.data))
        # Find all paragraphs
        paragraphs = textdoc.getElementsByType(odf_text.P)  # type: ignore
        ptexts = [teletype.extractText(p) for p in paragraphs]  # type: ignore
        return "\n\n".join(ptexts)


# Map file mime type to document class
MIMETYPE_TO_DOC_CLASS: Dict[str, DocumentType] = {
    "text/plain": PlainTextDocument,
    "text/html": HTMLDocument,
    "text/rtf": RTFDocument,
    "application/pdf": PDFDocument,
    "application/x-pdf": PDFDocument,
    "application/rtf": RTFDocument,
    "application/vnd.oasis.opendocument.text": ODTDocument,
    # Yes, really! Mime type naming by committee...
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxDocument,
}

SUPPORTED_DOC_MIMETYPES = frozenset(MIMETYPE_TO_DOC_CLASS.keys())


def doc_class_for_mime_type(mime_type: str) -> DocumentType:
    assert mime_type in SUPPORTED_DOC_MIMETYPES
    return MIMETYPE_TO_DOC_CLASS[mime_type]


SUFFIX_TO_DOC_CLASS: Mapping[str, DocumentType] = {
    "txt": PlainTextDocument,
    "html": HTMLDocument,
    "rtf": RTFDocument,
    "pdf": PDFDocument,
    "odt": ODTDocument,
    "docx": DocxDocument,
}

SUPPORTED_DOC_SUFFIXES = frozenset(SUFFIX_TO_DOC_CLASS.keys())


def doc_class_for_suffix(suffix: str) -> Type[Document]:
    assert suffix in SUPPORTED_DOC_SUFFIXES
    return SUFFIX_TO_DOC_CLASS[suffix]
