# Korean support

myeonggipop is Korean-only: lookup always uses Korean separators, jamo
pre/post-processing and Korean deconjugation rules. Just import a Korean
dictionary — no configuration needed.

## Quick start

1. Download a Korean Yomitan dictionary, e.g. KRDICT EN from
   [Lyroxide/yomitan-ko-dic](https://github.com/Lyroxide/yomitan-ko-dic/releases)
   (CC BY-SA 2.0 KR, National Institute of Korean Language data).
   Both the full build and the `No.Examples` build work; the importer
   keeps only short translations either way.
   (Or build it yourself: `myeonggipop build-dict`.)
2. Import it:
   ```
   myeonggipop import-yomitan-dict-text KO-EN.KRDICT.zip
   ```
3. In the tray menu, select an OCR provider that reads Hangul:
   **Chrome Screen AI (local)** (the default), **Google Lens (remote)** or
   **owocr (Websocket)** with a Korean-capable backend (e.g. PaddleOCR
   `korean_PP-OCRv5`). If Screen AI components are missing the app falls
   back to Google Lens automatically.
4. Hover Korean text in games, videos or web pages as usual.

For video games where text hooking works, Textractor + Yomitan in a
browser remains an alternative; OCR covers everything else.

## How it works

* `scripts/deconjugator_ko.json` — 2682 Yomitan Korean deinflection rules
  (`yomitan/ext/js/language/ko/korean-transforms.js`) converted to
  myeonggipop's rule format by `scripts/build_korean_deconjugator.py`
  (`myeonggipop build-korean-deconjugator path/to/korean-transforms.js`).
  The conversion is exact: a differential test against a faithful
  reimplementation of Yomitan's `LanguageTransformer` produces identical
  candidate sets on all sampled words. One degenerate upstream rule
  (`suffixInflection('', '다', ...)` in `-로라`, which matches every
  string) is skipped — see the converter header.
* `dictionary/hangul.py` — exact Python port of hangul-js 0.2.6
  (MIT, (c) 2017 Jaemin Jo) `disassemble`/`assemble`. Lookup disassembles
  Hangul to jamo before deconjugation and reassembles candidates before
  the dictionary lookup, mirroring Yomitan's text pre/post-processors.
* `dictionary/lookup.py` — Korean separator set, jamo pre/post-processing
  around the deconjugator. POS validation is skipped for entries that
  carry no POS info (common in imported dictionaries); entries tagged
  `v`/`adj`/`ida` (as in KRDICT builds) are still validated.
* `ocr/providers/glensv2`, `ocr/providers/screenai` — OCR lines are
  kept when they contain Korean or CJK (Hanja) script; word spaces are
  preserved for eojeol boundaries.

## Popup display

KRDICT entries are imported in compact form: each sense stores only the
short translation (`cat`), so popups stay short. Two further display
rules in `gui/popup.py` apply to every dictionary:

* a gloss that repeats the entry headword has the echo stripped
  (`고양이|cat …` → `cat …`, `고1→ 물고` → `→ 물고`);
* sense numbers (`(1)`, `(2)`…) are only shown when an entry has more
  than one sense.

Two settings (Popup Content tab, `config.ini` Theme section)
bound popup length: `max_gloss_chars` (default 150, per sense,
ellipsis) and `max_senses_per_entry` (default 3, with a `+N more`
indicator). Set either to 0 for unlimited.

`show_hanja` (default on) renders 〔漢字〕 from the dictionary as a
header chip; `show_grammar_explanations` (default on) shows the verbose
KRDICT explanations, but only for grammar entries (endings, particles,
affixes) — content words always stay short. Both need a dictionary
imported with this version (the fields are stored at import time).

Note: the importer change requires re-importing the dictionary.
Display rules apply to already-imported dictionaries immediately.

## Limitations

* Frequency ranks come from the imported dictionary's meta banks; for
  Korean frequency consider additionally importing a CC100-based
  frequency dictionary (or rely on the KRDICT ⭐ level stars in tags).

## Spaces

Korean spaces are preserved end to end: Lens/ScreenAI
keep word boundaries (via the API separator or single spaces), hit-scan
counts them in character offsets, and lookup keeps them (only leading /
trailing whitespace is stripped). Deconjugation is unaffected — rules
match suffixes and prefix scanning handles each eojeol. The console
`Looking up: ...` line therefore shows readable spaced text. Note
`max_lookup_length` (default 25) counts spaces too; raise it for long
game dialogue lines. Particles on nouns are additionally covered by
longest-prefix scanning.

## Settings

*Show Tags* vs *Show Level Stars*: different parts of the same tag.
KRDICT tags look like `Noun ⭐⭐⭐` — Show Tags renders the words
(`Noun`), Show Level Stars renders the stars and also uses them for
sorting (starred senses and entries rank higher). There is no numeric
frequency display; the stars replace it.

Defaults: non-compact layout, everything shown (all glosses, Hanja,
grammar explanations and traces, tags, stars), 5 senses per entry,
150 chars per gloss, lookup length 50.

Hanja are stored per sense at import and shown next to the sense they
belong to (`number; figure 〔數〕`), never as a header union.

## Sources and licenses

* Deinflection rules: [yomidevs/yomitan](https://github.com/yomidevs/yomitan),
  GPL-3.0 (same license as myeonggipop).
* Jamo codec: [Hangul.js](https://github.com/e-/Hangul.js), MIT.
* KRDICT dictionary data: National Institute of Korean Language,
  CC BY-SA 2.0 KR.
