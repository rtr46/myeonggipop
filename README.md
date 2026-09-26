# myeonggipop - Korean OCR popup dictionary

> ⚠️ **Honest warning:** this is an experimental, AI-assisted fork. It works,
> but expect bugs, rough edges and half-finished corners. It is not stable
> software. Bug reports are welcome — polished PRs even more so.

myeonggipop is a fork of [meikipop](https://github.com/rtr46/meikipop)
retargeted from Japanese to **Korean**: point at Korean text anywhere on
your screen (games, videos, websites) and get instant dictionary lookups
with verb/adjective deinflection, Hanja and grammar explanations.

## Install & run

Isolated install (runs side by side with meikipop, no conflicts):

```
python -m venv .venv
.venv\Scripts\activate        # Windows  (or: source .venv/bin/activate)
pip install -e .
```

Build the dictionary yourself from KRDICT source data (~1 min, downloads
the public KRDICT release — there are no prebuilt myeonggipop dictionaries):

```
myeonggipop build-dict
```

Or import a Yomitan dictionary manually (e.g. KRDICT EN from
[Lyroxide/yomitan-ko-dic](https://github.com/Lyroxide/yomitan-ko-dic/releases)):

```
myeonggipop import-yomitan-dict-text KO-EN.KRDICT.zip
```

Then run it and hover over Korean text (default hotkey: shift):

```
myeonggipop
```

Right-click the tray icon for settings, scan region and OCR provider.
Default OCR is Chrome Screen AI (local, [setup](https://github.com/rtr46/meikipop/releases/tag/v1.10.0));
Google Lens is the automatic fallback. Settings and dictionary live in
`%LOCALAPPDATA%\myeonggipop\` — a different folder than meikipop's, so
both apps coexist peacefully.

## How it was made

* Korean deinflection: [Yomitan](https://github.com/yomidevs/yomitan)'s
  `korean-transforms.js` converted to myeonggipop rules
  (`myeonggipop build-korean-deconjugator`), verified identical against
  Yomitan's own transformer on 41 conjugated words.
* Jamo codec: Python port of [Hangul.js](https://github.com/e-/Hangul.js).
* Dictionary: KRDICT (full and No.Examples builds) imported in compact
  form — short translations, Hanja chips, full explanations for grammar
  words only. No frequency data shipped; KRDICT level stars (⭐⭐⭐) cover it.
* Details and knobs: [docs/KOREAN.md](docs/KOREAN.md).

## Credits & license

* Grammar rules: Yomitan, GPL-3.0.
* Jamo codec: Hangul.js, MIT (see notice in
  `src/myeonggipop/dictionary/hangul.py`).
* Dictionary data: 한국어기초사전 by the National Institute of Korean
  Language, [CC BY-SA 2.0 KR](https://krdict.korean.go.kr/kor/kboardPolicy/copyRightTermsInfo).
* This fork itself: GPL-3.0, see [LICENSE](LICENSE).
