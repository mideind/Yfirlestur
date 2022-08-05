[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7](https://img.shields.io/badge/python-3.7-blue.svg)](https://www.python.org/downloads/release/python-370/)
[![Join the chat at https://gitter.im/Greynir/Lobby](https://badges.gitter.im/Greynir/Lobby.svg)](https://gitter.im/Greynir/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Build](https://github.com/mideind/Yfirlestur/actions/workflows/python-app.yml/badge.svg)]()

<img src="static/img/yfirlestur-logo-large.png" alt="Yfirlestur" width="200" height="200"
  align="right" style="margin-left:20px; margin-bottom: 20px;">

# Yfirlestur

### Spelling and grammar correction for Icelandic

*Yfirlestur.is* is a public website where you can enter or submit your Icelandic text
and have it checked for spelling and grammar errors.

The tool also gives hints on words and structures that might not be appropriate,
depending on the intended audience for the text.

Try Yfirlestur (in Icelandic) at [https://yfirlestur.is](https://yfirlestur.is)!

<img src="static/img/yfirlestur-example-small.png" width="720" height="536"
  alt="Yfirlestur annotation" style="margin-top: 18px; margin-bottom: 6px">

*Text with annotations, as displayed by Yfirlestur.is*

The core spelling and grammar checking functionality of Yfirlestur.is is provided by the
[GreynirCorrect](https://github.com/mideind/GreynirCorrect) engine, by the same authors.
User feedback is greatly appreciated, either through GitHub Issues
or by e-mail to [mideind@mideind.is](mailto:mideind@mideind.is).

## HTTPS API

In addition to its graphical web front-end, Yfirlestur.is exposes a public
HTTPS/JSON application programming interface (API) to perform spelling and grammar
checking.

### From the command line

This API can for example by accessed by `curl` from the Linux/MacOS command line
as follows (try it!):

```bash
    $ curl https://yfirlestur.is/correct.api -d "text=Manninum á verkstæðinu vantar hamar"
```

...or, of course, via a HTTPS `POST` from your own code; see below.

All text is assumed to be coded in UTF-8.

The example returns the following JSON (shown indented, for ease of reading):

```json
{
  "result": [
    [
      {
        "annotations": [
          {
            "code":"P_WRONG_CASE_þgf_þf",
            "detail":"Sögnin 'að vanta' er ópersónuleg. Frumlag hennar á að vera í þolfalli í stað þágufalls.",
            "start":0,
            "end":2,
            "start_char":0,
            "end_char":21,
            "suggest":"Manninn á verkstæðinu",
            "text":"Á líklega að vera 'Manninn á verkstæðinu'"
          }
        ],
        "corrected":"Manninum á verkstæðinu vantar hamar",
        "tokens": [
          {"k":6,"x":"Manninum"},
          {"k":6,"x":"á"},
          {"k":6,"x":"verkstæðinu"},
          {"k":6,"x":"vantar"},
          {"k":6,"x":"hamar"}
        ]
      }
    ]
  ],
  "stats":
    {
      "ambiguity":1.0,
      "num_parsed":1,
      "num_sentences":1,
      "num_tokens":5
    },
  "text":"Manninum á verkstæðinu vantar hamar",
  "valid":true
}
```

The `result` field contains the result of the annotation, as a list of paragraphs,
each containing a list of sentences, each containing a list of annotations (under
the `annotations` field). Of course, if a sentence is correct and has no annotations,
its annotation list will be empty. An overview of error codes used in annotations is available [here](https://github.com/mideind/GreynirCorrect/blob/master/doc/errorcodes.rst).

Each sentence entry has a field containing a `corrected` version of it, where
likely errors have been corrected. The `corrected` string includes corrections
of most spelling errors but only a subset of suspected grammar errors;
the system is intentionally less aggressive about automatically applying those
(as can be seen in the example above).

Sentence entries also contain a list of `tokens`. The tokens
originate in the [Tokenizer package](https://github.com/mideind/Tokenizer) and contain the following fields:

`i`: Character index of token start.
`k`: Token type number, (WORD, DATEREL, AMOUNT, etc.). Mapping from numbers to strings is found in the documentation for the [Tokenizer package](https://github.com/mideind/Tokenizer).
`o`: Original token text.
`x`: Corrected text of token.

Other possible fields:
`s`: Stem of word. It can contain '-' if the stem is not found in BÍN and compound analysis has been used.
`c`: Part-of-speech (kk/kvk/hk, so, lo, ao, fs, st, etc.).
`b`: Inflectional form given in BÍN. Can be '-' if the word cannot be inflected.
`t`: Terminal that the token is connected to in the CFG.
`v`: Token value (if applicable). Number, amount, date or name of currency.
`f`: BÍN category (alm, ism, fyr, örn, etc.). 


Each annotation applies to a span of sentence tokens, starting
at the token whose index is
given in `start` and ending with the token whose index is
in `end`. Both indices are 0-based
and inclusive. Also, a starting character index is found
in `start_char` and an ending index in `end_char`. Again,
both are 0-based and inclusive. Note that these are character
indices within the original source string, not byte indices.

An annotation has a `code` which uniquely determines the type
of error or warning. If the code ends with `/w`, it is a warning, otherwise
it is an error.

An annotation has a short, human-readable `text` field which describes
the annotation succintly, as well as a `detail` field which has further detail
on the annotation, possibly containing grammatical explanations.

Finally, some annotations contain a `suggest` field with text that could
replace the text within the token span, if the user agrees with
the suggestion being made.

The result JSON further includes a `stats` field with information about
the annotation job, such as the number of tokens and sentences processed,
and how many of those sentences could be parsed. The `valid` field is
`true` if the request was correctly formatted and could be processed
without error, or `false` if there was a problem.

#### Options

The `/correct.api` endpoint supports several options:

| Key                           | Type | Default | Explanation
| ----------------------------- | ---- | ------- | ------------------------------
| annotate\_unparsed\_sentences | bool | true    | Annotate sentence even when parsing fails
| suppress_suggestions          | bool | false   | Don't return suggestions
| ignore_wordlist               | list | []      | Words to accept without comment
| ignore_rules                  | list | []      | Rules to ignore when annotating

### From Python

As an example of accessing the Yfirlestur API from Python, here is
a short demo program which submits two paragraphs of text to the
spelling and grammar checker:

```python
# $ pip install requests
import requests
import json

# The text to check, two paragraphs of two and one sentences, respectively
my_text = (
    "Manninum á verkstæðinu vanntar hamar. Guðjón setti kókið í kælir.\n"
    "Mér dreimdi stórann brauðhleyf."
)

# Make the POST request, submitting the text
rq = requests.post("https://yfirlestur.is/correct.api", data=dict(text=my_text))

# Retrieve the JSON response
resp = rq.json()

# Enumerate through the returned paragraphs, sentences and annotations
for ix, pg in enumerate(resp["result"]):
    print(f"\n{ix+1}. efnisgrein")
    for sent in pg:
        print(f"   {sent['corrected']}")
        for ann in sent["annotations"]:
            print(
                f"      {ann['start']:03} {ann['end']:03} "
                f"{ann['code']:20} {ann['text']}"
            )
```

This program prints the following output:

```bash
$ python test.py

1. efnisgrein
   Manninum á verkstæðinu vantar hamar.
      000 002 P_WRONG_CASE_þgf_þf  Á líklega að vera 'Manninn á verkstæðinu'
      003 003 S004                 Orðið 'vanntar' var leiðrétt í 'vantar'
   Guðjón setti kókið í kælir.
      004 004 P_NT_EndingIR        Á sennilega að vera 'kæli'

2. efnisgrein
   Mér dreymdi stóran brauðhleif.
      000 000 P_WRONG_CASE_þgf_þf  Á líklega að vera 'Mig'
      001 001 S004                 Orðið 'dreimdi' var leiðrétt í 'dreymdi'
      002 002 S001                 Orðið 'stórann' var leiðrétt í 'stóran'
      003 003 S004                 Orðið 'brauðhleyf' var leiðrétt í 'brauðhleif'
```

The open source *GreynirCorrect* engine that powers Yfirlestur.is
is further [documented here](https://yfirlestur.is/doc/).

## Acknowledgements

Parts of this software are developed under the auspices of the
Icelandic Government's 5-year Language Technology Programme for Icelandic,
managed by Almannarómur. The LT Programme is described
[here](https://www.stjornarradid.is/lisalib/getfile.aspx?itemid=56f6368e-54f0-11e7-941a-005056bc530c)
(English version [here](https://clarin.is/media/uploads/mlt-en.pdf)).

## Copyright and licensing

Yfirlestur.is is Copyright © 2022 [Miðeind ehf.](https://mideind.is).
The original author of this software is *Vilhjálmur Þorsteinsson*.

<a href="https://mideind.is"><img src="static/img/mideind-horizontal-small.png" alt="Miðeind ehf."
    width="214" height="66" align="right" style="margin-left:20px; margin-bottom: 20px;"></a>

This software is licensed under the **MIT License**:

*Permission is hereby granted, free of charge, to any person*
*obtaining a copy of this software and associated documentation*
*files (the "Software"), to deal in the Software without restriction,*
*including without limitation the rights to use, copy, modify, merge,*
*publish, distribute, sublicense, and/or sell copies of the Software,*
*and to permit persons to whom the Software is furnished to do so,*
*subject to the following conditions:*

**The above copyright notice and this permission notice shall be**
**included in all copies or substantial portions of the Software.**

*THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,*
*EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF*
*MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.*
*IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY*
*CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,*
*TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE*
*SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.*

If you would like to use this software in ways that are incompatible
with the standard MIT license, [contact Miðeind ehf.](mailto:mideind@mideind.is)
to negotiate custom arrangements.
