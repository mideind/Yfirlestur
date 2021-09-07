"""

    Greynir: Natural language processing for Icelandic

    High-level tokenizer and named entity recognizer

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


    This module exports recognize_entities(), a function which
    adds a named entity recognition layer on top of the reynir.bintokenizer
    functionality.

    Named entity recognition requires access to the SQL scraper database
    and is thus not appropriate for inclusion in reynir.bintokenizer,
    as ReynirPackage does not (and should not) require a database to be present.

"""

from typing import Any, List, Iterator, Dict, Union, Tuple, Optional, Type, cast

from collections import defaultdict
import logging

from reynir import Abbreviations, TOK, Tok
from reynir.bindb import GreynirBin
from sqlalchemy.orm.query import Query as SqlQuery

from db import Session, SessionContext, OperationalError
from db.models import Entity


EntityNameList = List[Tuple[List[str], Entity]]
StateDict = Dict[Union[str, None], EntityNameList]


def recognize_entities(
    token_stream: Iterator[Tok],
    enclosing_session: Optional[Session] = None,
    token_ctor: Type[TOK] = TOK,
) -> Iterator[Tok]:

    """ Parse a stream of tokens looking for (capitalized) entity names
        The algorithm implements N-token lookahead where N is the
        length of the longest entity name having a particular initial word.
        Adds a named entity recognition layer on top of the
        reynir.bintokenizer.tokenize() function. """

    # Token queue
    tq: List[Tok] = []
    # Phrases we're considering. Note that an entry of None
    # indicates that the accumulated phrase so far is a complete
    # and valid known entity name.
    state: StateDict = defaultdict(list)
    # Entity definition cache
    ecache: Dict[str, List[Entity]] = dict()
    # Last name to full name mapping ('Clinton' -> 'Hillary Clinton')
    lastnames: Dict[str, Tok] = dict()

    with GreynirBin.get_db() as db, SessionContext(
        session=enclosing_session, commit=True, read_only=True
    ) as session:

        def fetch_entities(w: str, fuzzy: bool = True) -> List[Entity]:
            """Return a list of entities matching the word(s) given,
            exactly if fuzzy = False, otherwise also as a starting word(s)"""
            try:
                q: SqlQuery[Entity] = cast(Any, session).query(
                    Entity.name, Entity.verb, Entity.definition
                )
                if fuzzy:
                    q = cast(Any, q).filter(Entity.name.like(w + " %") | (Entity.name == w))  # type: ignore
                else:
                    q = cast(Any, q).filter(Entity.name == w)
                return q.all()
            except OperationalError as e:
                logging.warning("SQL error in fetch_entities(): {0}".format(e))
                return []

        def query_entities(w: str) -> List[Entity]:
            """Return a list of entities matching the initial word given"""
            e = ecache.get(w)
            if e is None:
                ecache[w] = e = fetch_entities(w)
            return e

        def lookup_lastname(lastname: str) -> Optional[Tok]:
            """ Look up a last name in the lastnames registry,
                eventually without a possessive 's' at the end, if present"""
            fullname = lastnames.get(lastname)
            if fullname is not None:
                # Found it
                return fullname
            # Try without a possessive 's', if present
            if lastname.endswith("s"):
                return lastnames.get(lastname[0:-1])
            # Nope, no match
            return None

        def flush_match() -> Tok:
            """Flush a match that has been accumulated in the token queue"""
            if len(tq) == 1 and lookup_lastname(tq[0].txt) is not None:
                # If single token, it may be the last name of a
                # previously seen entity or person
                return token_or_entity(tq[0])
            # Reconstruct original text behind phrase
            new_ent = token_ctor.Entity("")
            for ix, item in enumerate(tq):
                new_ent = new_ent.concatenate(item, separator=" " if ix > 0 else "")
            # We don't include the definitions in the token - they should be looked up
            # on the fly when processing or displaying the parsed article
            return new_ent

        def token_or_entity(token: Tok) -> Tok:
            """ Return a token as-is or, if it is a last name of a person
                that has already been mentioned in the token stream by full name,
                refer to the full name """
            assert token.txt[0].isupper()
            tfull = lookup_lastname(token.txt)
            if tfull is None:
                # Not a last name of a previously seen full name
                return token
            if tfull.kind != TOK.PERSON:
                # Return an entity token with no definitions
                # (this will eventually need to be looked up by full name when
                # displaying or processing the article)
                return token_ctor.Entity("").concatenate(token)
            # Return the full name meanings
            return token_ctor.Person("", tfull.person_names).concatenate(token)

        try:

            while True:

                token = next(token_stream)
                if not token.txt:  # token.kind != TOK.WORD:
                    if state:
                        if None in state:
                            yield flush_match()
                        else:
                            yield from tq
                        tq = []
                        state = defaultdict(list)
                    yield token
                    continue

                # Look for matches in the current state and build a new state
                newstate: StateDict = defaultdict(list)
                w = token.txt  # Original word

                def add_to_state(slist: List[str], entity: Entity) -> None:
                    """ Add the list of subsequent words to the new parser state """
                    wrd = slist[0] if slist else None
                    rest = slist[1:]
                    newstate[wrd].append((rest, entity))

                if w in state:
                    # This matches an expected token
                    tq.append(token)  # Add to lookahead token queue
                    # Add the matching tails to the new state
                    for sl, entity in state[w]:
                        add_to_state(sl, entity)
                    # Update the lastnames mapping
                    new_ent = token_ctor.Entity("")
                    for ix, item in enumerate(tq):
                        new_ent = new_ent.concatenate(
                            item, separator=" " if ix > 0 else ""
                        )
                    parts = new_ent.txt.split()
                    # If we now have 'Hillary Rodham Clinton',
                    # make sure we delete the previous 'Rodham' entry
                    for p in parts[1:-1]:
                        if p in lastnames:
                            del lastnames[p]
                    if parts[-1][0].isupper():
                        # 'Clinton' -> 'Hillary Rodham Clinton'
                        lastnames[parts[-1]] = new_ent
                else:
                    # Not a match for an expected token
                    if state:
                        if None in state:
                            # We have an accumulated match, but if the next token
                            # is an uppercase word without a BÍN meaning, we
                            # append it to the current entity regardless.
                            # This means that 'Charley Lucknow' is handled as a single
                            # new entity name even if 'Charley' already exists
                            # as an entity.
                            while w and w[0].isupper() and not token.val:
                                # Append to the accumulated token queue, which will
                                # be squashed to a single token in flush_match()
                                tq.append(token)
                                token = next(token_stream)
                                w = token.txt
                            # Flush the already accumulated match
                            yield flush_match()
                        else:
                            yield from tq
                        tq = []

                    # Add all possible new states for entity names
                    # that could be starting
                    weak = True
                    cnt = 1
                    upper = w and w[0].isupper()
                    parts: List[str] = []

                    if upper and " " in w:
                        # For all uppercase phrases (words, entities, persons),
                        # maintain a map of last names to full names
                        parts = w.split()
                        lastname = parts[-1]
                        # Clinton -> Hillary [Rodham] Clinton
                        if lastname[0].isupper():
                            # Look for Icelandic patronyms/matronyms
                            _, m = db.lookup_g(lastname, False)
                            if m and any(mm.fl in {"föð", "móð"} for mm in m):
                                # We don't store Icelandic patronyms/matronyms
                                # as surnames
                                pass
                            else:
                                lastnames[lastname] = token

                    elist: List[Entity] = []
                    if token.kind == TOK.WORD and upper and w not in Abbreviations.DICT:
                        if " " in w:
                            # w may be a person name with more than one embedded word
                            # parts is assigned in the if statement above
                            cnt = len(parts)
                        elif not token.has_meanings or ("-" in token.meanings[0].stofn):
                            # No BÍN meaning for this token, or the meanings
                            # were constructed by concatenation (indicated by a hyphen
                            # in the stem)
                            weak = False  # Accept single-word entity references
                        # elist is a list of Entity instances
                        elist = query_entities(w)

                    if elist:
                        # This word might be a candidate to start an entity reference
                        candidate = False
                        for e in elist:
                            # List of subsequent words in entity name
                            sl = e.name.split()[cnt:]
                            if sl:
                                # Here's a candidate for a longer entity reference
                                # than we already have
                                candidate = True
                            if sl or not weak:
                                add_to_state(sl, e)
                        if weak and not candidate:
                            # Found no potential entity reference longer than this token
                            # already is - and we have a BÍN meaning for it:
                            # Abandon the effort
                            assert not newstate
                            assert not tq
                            yield token_or_entity(token)
                        else:
                            # Go for it: Initialize the token queue
                            tq = [token]
                    else:
                        # Not a start of an entity reference: simply yield the token
                        assert not tq
                        if upper:
                            # Might be a last name referring to a full name
                            yield token_or_entity(token)
                        else:
                            yield token

                # Transition to the new state
                state = newstate

        except StopIteration:
            # Token stream is exhausted
            pass

        # Yield an accumulated match if present
        if state:
            if None in state:
                yield flush_match()
            else:
                yield from tq
            tq = []

    assert not tq
