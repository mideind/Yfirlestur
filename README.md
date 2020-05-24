[![Join the chat at https://gitter.im/Greynir/Lobby](https://badges.gitter.im/Greynir/Lobby.svg)](https://gitter.im/Greynir/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

<img src="static/img/yfirlestur-logo-large.png" alt="Yfirlestur" width="200" height="140" align="right" style="margin-left:20px; margin-bottom: 20px;">

# Yfirlestur

### Spelling and grammar correction for Icelandic

*Yfirlestur.is* is a public website where you can enter or submit your Icelandic text
and have it checked for spelling and grammar errors. The tool also gives
hints on words and structures that might not be appropriate, depending
on the intended audience for the text.

Try Yfirlestur (in Icelandic) at [https://yfirlestur.is](https://yfirlestur.is)!

<a href="https://raw.githubusercontent.com/mideind/Yfirlestur/master/static/img/yfirlestur-example.png?raw=true" title="Yfirlestur annotation">
<img src="static/img/yfirlestur-example-small.png" width="400" height="298" alt="Yfirlestur annotation" style="margin-top: 10px; margin-bottom: 10px">
</a>

*Text with annotations, as displayed by Yfirlestur.is*

The core spelling and grammar checking functionality of Yfirlestur.is is provided by the
[GreynirCorrect](https://github.com/mideind/GreynirCorrect) engine, by the same authors.

## HTTPS API

Yfirlestur.is provides an HTTPS application programming interface (API) based on JSON.
This API can for example by accessed by `curl` as follows:

```
    $ curl https://yfirlestur.is/correct.api -d "text=Manninum á verkstæðinu vantar hamar"
```

...or, of course, by a HTTPS `POST` from your own code. All text is assumed to be coded in UTF-8.

The example returns the following JSON (formatted for ease of reading):

```
{
    "result": [
        [
            {
                "annotations": [
                    {
                        "code":"P_WRONG_CASE_þgf_þf",
                        "detail":"Sögnin 'að vanta' er ópersónuleg. Frumlag hennar á að vera í þolfalli í stað þágufalls.",
                        "end":2,
                        "start":0,
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
the `annotations` field). Of course, if a sentence has no annotations, its annotation
list will be empty.

Each sentence has a field containing a `corrected` version of it, where all
likely errors have been corrected, as well as a list of `tokens`. The tokens
originate in the [Tokenizer package](https://github.com/mideind/Tokenizer)
and are documented there.

Each annotation applies to a span of sentence tokens, starting with the index
given in `start` and ending with the index in `end`. Both indices are 0-based
and inclusive. An annotation has a `code` which uniquely determines the type
of error or warning. If the code ends with `/w`, it is a warning, otherwise
it is an error.

An annotation has a short, human-readable `text` field which describes
the annotation succintly, as well as a `detail` field which has further detail
on the annotation, possibly containing grammatical explanations.

Finally, some annotations contain a `suggest` field with text that could
replace the text within the token span, if the user agrees with
the suggestion being made.

The result JSON further contains a `stats` field with information about
the annotation job, such as the number of tokens and sentences processed,
and how many of those sentences could be parsed. The `valid` field is
`true` if the request was correctly formatted and could be processed
without error, or `false` if there was a problem.


## Copyright and licensing

Yfirlestur is copyright © 2020 [Miðeind ehf.](https://mideind.is)
The original author of this software is *Vilhjálmur Þorsteinsson*.

<img src="static/img/GPLv3.png" align="right" style="margin-left:20px;">

This set of programs is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any later
version.

This set of programs is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
A PARTICULAR PURPOSE. See the GNU General Public License for more details.

The full text of the GNU General Public License v3 is
[included here](https://github.com/mideind/Yfirlestur/blob/master/LICENSE)
and also available here: [https://www.gnu.org/licenses/gpl-3.0.html](https://www.gnu.org/licenses/gpl-3.0.html).

If you wish to use this set of programs in ways that are not covered under the
GNU GPLv3 license, please contact us at [mideind@mideind.is](mailto:mideind@mideind.is)
to negotiate a custom license. This applies for instance if you want to include or use
this software, in part or in full, in other software that is not licensed under
GNU GPLv3 or other compatible licenses.
