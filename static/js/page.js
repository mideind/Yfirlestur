/*

   Yfirlestur: Online spelling and grammar correction for Icelandic

   Page.js

   Scripts for displaying tokenized and parsed text,
   with pop-up tags on hover, name registry, statistics, etc.

   Copyright (C) 2022 Miðeind ehf.

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


   For details about the token JSON format, see TreeUtility.dump_tokens() in treeutil.py.
   t.x is original token text.
   t.k is the token kind (TOK_x). If omitted, this is TOK_WORD.
   t.t is the name of the matching terminal, if any.
   t.m is the BÍN meaning of the token, if any, as a tuple as follows:
      t.m[0] is the lemma (stofn)
      t.m[1] is the word category (ordfl)
      t.m[2] is the word subcategory (fl)
      t.m[3] is the word meaning/declination (beyging)
   t.v contains auxiliary information, depending on the token kind
   t.err is 1 if the token is an error token

*/

// Punctuation types

var TP_LEFT = 1;
var TP_CENTER = 2;
var TP_RIGHT = 3;
var TP_NONE = 4; // Tight - no whitespace around
var TP_WORD = 5;

// Token spacing

var TP_SPACE = [
   // Next token is:
   // LEFT    CENTER  RIGHT   NONE    WORD
   // Last token was TP_LEFT:
   [false, true, false, false, false],
   // Last token was TP_CENTER:
   [true, true, true, true, true],
   // Last token was TP_RIGHT:
   [true, true, false, false, true],
   // Last token was TP_NONE:
   [false, true, false, false, false],
   // Last token was TP_WORD:
   [true, true, false, false, true]
];

var LEFT_PUNCTUATION = "([„«#$€<";
var RIGHT_PUNCTUATION = ".,:;)]!%?“»”’…°>";
var NONE_PUNCTUATION = "—–-/'~‘\\";
// CENTER_PUNCTUATION = '"*&+=@©|'

// Location word categories
var LOC_FL = ["lönd", "örn", "göt", "borg"];
var FL_TO_LOC_DESC = {
   "lönd": "land",
   "örn": "örnefni",
   "göt": "götuheiti",
   "borg": "borg"
};
var FL_TO_LOC_KIND = {
   "lönd": "country",
   "örn": "placename",
   "göt": "street",
   "borg": "placename"
};

// Token array
var w = [];

// Name dictionary
var nameDict = {};

function debugMode() {
   return false;
}

function spacing(t) {
   // Determine the spacing requirements of a token
   if (t.k != TOK_PUNCTUATION)
      return TP_WORD;
   if (LEFT_PUNCTUATION.indexOf(t.x) > -1)
      return TP_LEFT;
   if (RIGHT_PUNCTUATION.indexOf(t.x) > -1)
      return TP_RIGHT;
   if (NONE_PUNCTUATION.indexOf(t.x) > -1)
      return TP_NONE;
   return TP_CENTER;
}

function queryPerson(name, ev) {
   // Navigate to the main page with a person query
   openURL("/?f=q&q=" + encodeURIComponent("Hver er " + name + "?"), ev);
}

function queryEntity(name, ev) {
   // Navigate to the main page with an entity query
   openURL("/?f=q&q=" + encodeURIComponent("Hvað er " + name + "?"), ev);
}

function queryLocation(name, ev) {
   // TODO: Implement me!
}

function showParse(ev) {
   // A sentence has been clicked: show its parse grid
   var sentText = $(ev.delegateTarget).text();
   openURL("https://greynir.is/treegrid?txt=" + encodeURIComponent(sentText), ev);
}

function showPerson(ev) {
   // A person name has been clicked
   var name = undefined;
   var wId = $(this).attr("id"); // Check for token id
   if (wId !== undefined) {
      // Obtain the name in nominative case from the token
      var ix = parseInt(wId.slice(1));
      if (w[ix] !== undefined) {
         name = w[ix].v;
      }
   }
   if (name === undefined) {
      name = $(this).text(); // No associated token: use the contained text
   }
   queryPerson(name, ev);
}

function showEntity(ev) {
   // An entity name has been clicked
   var ename = $(this).text();
   var nd = nameDict[ename];
   if (nd && nd.kind == "ref") {
      // Last name reference to a full name entity
      // ('Clinton' -> 'Hillary Rodham Clinton')
      // In this case, we assume that we're asking about a person
      queryPerson(nd.fullname, ev);
   } else {
      queryEntity(ename, ev);
   }
}

function hoverIn() {
   // Hovering over a token
   var wId = $(this).attr("id");
   if (wId === null || wId === undefined) {
      // No id: nothing to do
      return;
   }
   var ix = parseInt(wId.slice(1));
   var t = w[ix];
   if (!t) {
      // No token: nothing to do
      return;
   }
   // Save our position
   var offset = $(this).position();
   // Highlight the token
   $(this).addClass("highlight");

   // Get token info
   var r = tokenInfo(t, nameDict);

   if (!r.grammar && !r.lemma && !r.details) {
      // Nothing interesting to show (probably the sentence didn't parse)
      return;
   }

   $("#grammar").html(r.grammar || "").show();
   $("#lemma").text(r.lemma || "").show();
   $("#details").text(r.details || "").show();

   // Display the percentage bar if we have percentage info
   if (r.percent !== null) {
      makePercentGraph(r.percent);
   } else {
      $("#percent").hide();
   }

   $("#info").removeClass();
   if (r.class) {
      $("#info").addClass(r.class);
   }

   // If foreign currency amount, show rough equivalent in ISK
   if (t.k == TOK_AMOUNT && t.v[1] !== "ISK") {
      getCurrencyValue(t.v[1], function (val) {
         if (val !== undefined) {
            var desc = friendlyISKDescription(t.v[0] * val);
            $("#details").html($("#details").text() + "<br>" + desc);
         }
      });
   }

   // Try to fetch image if person (and at least two names)
   if (t.k == TOK_PERSON && t.v.split(' ').length > 1) {
      getPersonImage(r.lemma, function (img) {
         $("#info-image").html(
            $("<img>").attr('src', img[0])
         ).show();
      });
   }

   if (t["m"]) {
      var fl = t["m"][2];

      // It's a location. Display loc info.
      if (LOC_FL.includes(fl)) {
         $('#grammar').hide();
         $('#details').html(FL_TO_LOC_DESC[fl]);
         r.tagClass = "glyphicon-globe";

         var name = r.lemma;
         var kind = FL_TO_LOC_KIND[fl];

         // Query server for more information about location
         getLocationInfo(name, kind, function (info) {
            // We know which country, show flag image
            if (info['country']) {
               $('#lemma').append(
                  $("<img>").attr('src', '/static/img/flags/' + info['country'] + '.png').attr('class', 'flag')
               );
            }
            // Description
            if (info['desc']) {
               $('#details').html(info['desc']);
            }
            // Map image
            if (info['map']) {
               $("#info-image").html(
                  $("<img>").attr('src', info['map']).attr('onerror', '$(this).hide();')
               ).show();
            }
         });
      }
   }

   $("#info span#tag")
      .removeClass()
      .addClass("glyphicon")
      .addClass(r.tagClass ? r.tagClass : "glyphicon-tag");

   // Position the info popup
   $("#info")
      .css("top", "" + offset.top + "px")
      .css("left", "" + offset.left + "px")
      .css("visibility", "visible");
}

function getLocationInfo(name, kind, successFunc) {
   var ckey = kind + '_' + name;
   var cache = getLocationInfo.cache;
   if (cache === undefined) {
      cache = {};
      getLocationInfo.cache = cache;
   }
   // Retrieve from cache
   if (cache[ckey] !== undefined) {
      if (cache[ckey]) {
         successFunc(cache[ckey]);
      }
      return;
   }
   // Abort any ongoing request
   if (getLocationInfo.request) {
      getLocationInfo.request.abort();
   }
   // Ask server for location info
   var data = { name: name, kind: kind };
   getLocationInfo.request = $.getJSON("/locinfo", data, function (r) {
      cache[ckey] = null;
      if (r['found']) {
         cache[ckey] = r;
         successFunc(r);
      }
   });
}

function getPersonImage(name, successFunc) {
   var cache = getPersonImage.imageCache;
   if (cache === undefined) {
      cache = {};
      getPersonImage.imageCache = cache;
   }
   // Retrieve from cache
   if (cache[name] !== undefined) {
      if (cache[name]) {
         successFunc(cache[name]);
      }
      return;
   }
   // Abort any ongoing image request
   if (getPersonImage.request) {
      getPersonImage.request.abort();
   }
   // Ask server for thumbnail image
   var enc = encodeURIComponent(name);
   getPersonImage.request = $.getJSON("/image?thumb=1&name=" + enc, function (r) {
      cache[name] = null;
      if (r['found']) {
         cache[name] = r['image'];
         successFunc(r['image']);
      }
   });
}

function hoverOut() {
   // Stop hovering over a word
   $("#info").css("visibility", "hidden");
   $("#info-image").hide();
   $(this).removeClass("highlight");
   // Abort any ongoing onhover requests to server.
   // These requests are stored as properties of
   // the functions that sent them.
   var reqobjs = [getPersonImage, getLocationInfo];
   for (var idx in reqobjs) {
      if (reqobjs[idx] && reqobjs[idx].request) {
         reqobjs[idx].request.abort();
         reqobjs[idx].request = null;
      }
   }
}

function displayTokens(j) {
   // Generate HTML for the token list given in j,
   // and insert it into the <div> with id 'pgs'.
   // Also, populate the global w array with the
   // token list.
   var x = ""; // Result text
   var lastSp;
   w = [];
   if (j !== null)
      $.each(j, function (pix, p) {
         // Paragraph p
         x += "<p>\n";
         $.each(p, function (six, s) {
            // Sentence s
            var err = false;
            lastSp = TP_NONE;
            // Check whether the sentence has an error or was fully parsed
            $.each(s, function (tix, t) {
               if (t.err == 1) {
                  err = true;
                  return false; // Break the iteration
               }
            });
            if (err)
               x += "<span class='sent err'>";
            else
               x += "<span class='sent parsed'>";
            $.each(s, function (tix, t) {
               // Token t
               var thisSp = spacing(t);
               // Insert a space in front of this word if required
               // (but never at the start of a sentence)
               if (TP_SPACE[lastSp - 1][thisSp - 1] && tix)
                  x += " ";
               lastSp = thisSp;
               if (t.err)
                  // Mark an error token
                  x += "<span class='errtok'>";
               if (t.k == TOK_PUNCTUATION)
                  // Add space around em-dash
                  x += "<i class='p'>" + ((t.x == "—") ? " — " : t.x) + "</i>";
               else {
                  var cls;
                  var tx = t.x;
                  var first = t.t ? t.t.split("_")[0] : undefined;
                  if (first == "sequence") {
                     // Special case to display tokens matching 'sequence' terminals
                     cls = " class='sequence'";
                  }
                  else
                     if (!t.k) {
                        // TOK_WORD
                        if (err)
                           // If the sentence was not parsed successfully,
                           // we don't have an unambiguous interpretation of
                           // the token (PoS tag or terminal name)
                           cls = "";
                        else
                           if (t.m) {
                              // Word class (noun, verb, adjective...)
                              cls = " class='" + t.m[1] + ' ' + t.m[2] + "'";
                           }
                           else
                              if (first == "sérnafn") {
                                 // Special case to display 'sérnafn' as 'entity'
                                 cls = " class='entity'";
                                 tx = tx.replace(" - ", "-"); // Tight hyphen, no whitespace
                              }
                              else
                                 // Not found
                                 cls = " class='nf'";
                     }
                     else {
                        cls = " class='" + tokClass[t.k] + "'";
                        if (t.k == TOK_ENTITY)
                           tx = tx.replace(" - ", "-"); // Tight hyphen, no whitespace
                     }
                  x += "<i id='w" + w.length + "'" + cls + ">" + tx + "</i>";
               }
               if (t.err)
                  x += "</span>";
               // Append to word/token list
               w.push(t);
            });
            // Finish sentence
            x += "</span>\n";
         });
         // Finish paragraph
         x += "</p>\n";
      });
   // Show the page text
   $("div#pgs").html(x);
   // Put a hover handler on each word
   $("div#pgs i").hover(hoverIn, hoverOut);
   // Put a click handler on each sentence
   $("span.sent").click(showParse);
   // Separate click handler on entity names
   $("i.entity").click(showEntity);
   // Separate click handler on person names
   $("i.person").click(showPerson);
}

function populateReadability(readabilityStats) {
	// "readability_stats": {
	// 	"flesch_kincaid_score": 57.539608466933885,
	// 	"flesch_kincaid_feedback": "Svolítið þungur texti"
	// }
  // if readability is not null, make the block visible
  if (readabilityStats !== null) {
    $("div#readability").css("display", "block");
    // flesch-kincaid-feedback 
    $("#flesch-kincaid-feedback").text(readabilityStats.flesch_kincaid_feedback);
    // flesch-kincaid-score
    $("#flesch-kincaid-score").text(readabilityStats.flesch_kincaid_score);
  } else {
    // Hide the readability block
    $("div#readability").css("display", "none");
  }
}

function populateRareWords(rareWords) {
  // this is a list
  // if rareWords is not null, make the block visible
  if (rareWords !== null) {
    $("div#rare-words").css("display", "block");
    // for each word in the list, add a list item to: <ul id="rare-words-list">
    $("#rare-words-list").html("");
    $.each(rareWords, function (index, word) {
      $("#rare-words-list").append("<li>" + word + "</li>");
    });

  } else {
    // Hide the rare words block
    $("div#rare-words").css("display", "none");
  } 

}
function populateStats(stats) {
   $("#tok-num").text(format_is(stats.num_tokens));
   $("#num-sent").text(format_is(stats.num_sentences));
   $("#num-parsed-sent").text(format_is(stats.num_parsed));
   if (stats.num_parsed == 1) {
      $("#paragraphs").text("málsgrein")
   } else {
      $("#paragraphs").text("málsgreinar");
   }
   if (stats.num_sentences > 0) {
      $("#num-parsed-ratio").text(format_is(100.0 * stats.num_parsed / stats.num_sentences, 1));
   } else {
      $("#num-parsed-ratio").text("0.0");
   }
   // $("#avg-ambig-factor").text(format_is(stats.ambiguity, 2));
   $("div#statistics").css("display", "block");
}

function populateRegister() {
   // Populate the name register display
   var i, item, name, title;
   var register = [];
   $("#namelist").html("");
   $.each(nameDict, function (name, desc) {
      // kind is 'ref', 'name' or 'entity'
      if (desc.kind != "ref")
         // We don't display references to full names
         // Whitespace around hyphens is eliminated for display
         register.push(
            {
               name: name.replace(" - ", "-"),
               title: desc.title,
               kind: desc.kind
            }
         );
   });
   register.sort(function (a, b) {
      return a.name.localeCompare(b.name);
   });
   for (i = 0; i < register.length; i++) {
      var ri = register[i];
      item = $("<li></li>");
      name = $("<span></span>").addClass(ri.kind).text(ri.name);
      item.append(name);
      if (ri.title) {
         title = $("<span></span>").addClass("title").text(ri.title);
         item.append(title);
      }
      $("#namelist").append(item);
   }
   // Display the register
   if (register.length) {
      $("#register").css("display", "block");
      $("#namelist span.name").click(function (ev) {
         // Send a person query to the server
         queryPerson($(this).text(), ev);
      });
      $("#namelist span.entity").click(function (ev) {
         // Send an entity query to the server
         queryEntity($(this).text(), ev);
      });
   }
}
