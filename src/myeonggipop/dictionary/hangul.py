# hangul.py
"""
Hangul syllable <-> jamo conversion, ported from hangul-js 0.2.6
(https://github.com/e-/Hangul.js).

Yomitan's Korean deinflection rules operate on *disassembled* compatibility
jamo, so this module must be behaviorally identical to
``Hangul.disassemble(str, false).join('')`` and ``Hangul.assemble(str)``.
All jamo below are Hangul Compatibility Jamo (U+3131-U+3163).

hangul-js license (MIT, Copyright (c) 2017 Jaemin Jo):

    Permission is hereby granted, free of charge, to any person obtaining
    a copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to
    the following conditions:

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

# Choseong (initials) in syllable composition order
_CHO = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ',
    'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ',
    'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ',
    'ㅍ', 'ㅎ',
]

# Jungseong (medials); complex vowels are stored split, exactly like hangul-js
_JUNG = [
    'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ',
    'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', ('ㅗ', 'ㅏ'), ('ㅗ', 'ㅐ'),
    ('ㅗ', 'ㅣ'), 'ㅛ', 'ㅜ', ('ㅜ', 'ㅓ'), ('ㅜ', 'ㅔ'), ('ㅜ', 'ㅣ'),
    'ㅠ', 'ㅡ', ('ㅡ', 'ㅣ'), 'ㅣ',
]

# Jongseong (finals), index 0 = no final; complex finals stored split
_JONG = [
    '', 'ㄱ', 'ㄲ', ('ㄱ', 'ㅅ'), 'ㄴ', ('ㄴ', 'ㅈ'), ('ㄴ', 'ㅎ'), 'ㄷ', 'ㄹ',
    ('ㄹ', 'ㄱ'), ('ㄹ', 'ㅁ'), ('ㄹ', 'ㅂ'), ('ㄹ', 'ㅅ'), ('ㄹ', 'ㅌ'),
    ('ㄹ', 'ㅍ'), ('ㄹ', 'ㅎ'), 'ㅁ', 'ㅂ', ('ㅂ', 'ㅅ'), 'ㅅ', 'ㅆ', 'ㅇ',
    'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]

_HANGUL_OFFSET = 0xAC00

_CONSONANTS = [
    'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄸ',
    'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ',
    'ㅁ', 'ㅂ', 'ㅃ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ',
    'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]

_COMPLETE_CHO = list(_CHO)

_COMPLETE_JUNG = [
    'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ',
    'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ', 'ㅙ',
    'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ',
    'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ',
]

_COMPLETE_JONG = [
    '', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ',
    'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ',
    'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]

_COMPLEX_CONSONANTS = [
    ('ㄱ', 'ㅅ', 'ㄳ'),
    ('ㄴ', 'ㅈ', 'ㄵ'),
    ('ㄴ', 'ㅎ', 'ㄶ'),
    ('ㄹ', 'ㄱ', 'ㄺ'),
    ('ㄹ', 'ㅁ', 'ㄻ'),
    ('ㄹ', 'ㅂ', 'ㄼ'),
    ('ㄹ', 'ㅅ', 'ㄽ'),
    ('ㄹ', 'ㅌ', 'ㄾ'),
    ('ㄹ', 'ㅍ', 'ㄿ'),
    ('ㄹ', 'ㅎ', 'ㅀ'),
    ('ㅂ', 'ㅅ', 'ㅄ'),
]

_COMPLEX_VOWELS = [
    ('ㅗ', 'ㅏ', 'ㅘ'),
    ('ㅗ', 'ㅐ', 'ㅙ'),
    ('ㅗ', 'ㅣ', 'ㅚ'),
    ('ㅜ', 'ㅓ', 'ㅝ'),
    ('ㅜ', 'ㅔ', 'ㅞ'),
    ('ㅜ', 'ㅣ', 'ㅟ'),
    ('ㅡ', 'ㅣ', 'ㅢ'),
]


def _make_hash(array):
    # Later entries overwrite earlier ones for duplicate code points,
    # mirroring hangul-js _makeHash (which also seeds {0: 0}).
    h = {0: 0}
    for i, ch in enumerate(array):
        if ch:
            h[ord(ch)] = i
    return h


_CONSONANTS_HASH = _make_hash(_CONSONANTS)
_CHO_HASH = _make_hash(_COMPLETE_CHO)
_JUNG_HASH = _make_hash(_COMPLETE_JUNG)
_JONG_HASH = _make_hash(_COMPLETE_JONG)


def _make_complex_hash(array):
    h = {}
    for a, b, c in array:
        h.setdefault(ord(a), {})[ord(b)] = ord(c)
    return h


_COMPLEX_CONSONANTS_HASH = _make_complex_hash(_COMPLEX_CONSONANTS)
_COMPLEX_VOWELS_HASH = _make_complex_hash(_COMPLEX_VOWELS)


def _is_consonant(c):
    return c in _CONSONANTS_HASH


def _is_cho(c):
    return c in _CHO_HASH


def _is_jung(c):
    return c in _JUNG_HASH


def _is_jong(c):
    return c in _JONG_HASH


def _is_hangul(c):
    return 0xAC00 <= c <= 0xD7A3


def _is_jung_joinable(a, b):
    inner = _COMPLEX_VOWELS_HASH.get(a)
    if inner and b in inner:
        return inner[b]
    return False


def _is_jong_joinable(a, b):
    inner = _COMPLEX_CONSONANTS_HASH.get(a)
    if inner and b in inner:
        return inner[b]
    return False


def disassemble(string, grouped=False):
    """
    Split Hangul syllables into compatibility jamo.
    Mirrors ``Hangul.disassemble(string, grouped)``.
    Returns a flat list of single characters (grouped=False) or a list
    of per-syllable lists (grouped=True).
    """
    if isinstance(string, list):
        string = ''.join(string)
    result = []
    for ch in string:
        temp = []
        code = ord(ch)
        if _is_hangul(code):
            code -= _HANGUL_OFFSET
            jong = code % 28
            jung = ((code - jong) // 28) % 21
            cho = (code - jong) // 28 // 21
            temp.append(_CHO[cho])
            jung_entry = _JUNG[jung]
            if isinstance(jung_entry, tuple):
                temp.extend(jung_entry)
            else:
                temp.append(jung_entry)
            if jong > 0:
                jong_entry = _JONG[jong]
                if isinstance(jong_entry, tuple):
                    temp.extend(jong_entry)
                else:
                    temp.append(jong_entry)
        elif _is_consonant(code):
            if _is_cho(code):
                r = _CHO[_CHO_HASH[code]]
            else:
                r = _JONG[_JONG_HASH[code]]
            if isinstance(r, str):
                temp.append(r)
            else:
                temp.extend(r)
        elif _is_jung(code):
            r = _JUNG[_JUNG_HASH[code]]
            if isinstance(r, str):
                temp.append(r)
            else:
                temp.extend(r)
        else:
            temp.append(ch)
        if grouped:
            result.append(temp)
        else:
            result.extend(temp)
    return result


def disassemble_to_string(string):
    """Mirrors ``Hangul.disassemble(str, false).join('')``."""
    if not isinstance(string, str):
        return ''
    return ''.join(disassemble(string))


def assemble(jamo):
    """
    Recompose compatibility jamo into Hangul syllables.
    Mirrors ``Hangul.assemble``. Accepts a string or a list of
    single-character strings.
    """
    if isinstance(jamo, str):
        array = disassemble(jamo)
    else:
        array = list(jamo)

    result = []
    length = len(array)
    stage = 0
    complete_index = -1
    previous_code = None
    jong_joined = False

    def make_hangul(index):
        nonlocal complete_index, jong_joined
        jong_joined = False
        if complete_index + 1 > index:
            return
        step = 1
        while True:
            if step == 1:
                cho = ord(array[complete_index + step])
                if _is_jung(cho):
                    if (complete_index + step + 1 <= index
                            and _is_jung(ord(array[complete_index + step + 1]))):
                        jung1 = ord(array[complete_index + step + 1])
                        result.append(chr(_is_jung_joinable(cho, jung1)))
                        complete_index = index
                        return
                    result.append(array[complete_index + step])
                    complete_index = index
                    return
                elif not _is_cho(cho):
                    result.append(array[complete_index + step])
                    complete_index = index
                    return
                hangul = array[complete_index + step]
            elif step == 2:
                jung1 = ord(array[complete_index + step])
                if _is_cho(jung1):
                    cho = _is_jong_joinable(cho, jung1)
                    result.append(chr(cho))
                    complete_index = index
                    return
                hangul = chr(((_CHO_HASH[cho] * 21) + _JUNG_HASH[jung1]) * 28 + _HANGUL_OFFSET)
            elif step == 3:
                jung2 = ord(array[complete_index + step])
                joined = _is_jung_joinable(jung1, jung2)
                if joined:
                    jung1 = joined
                    jong1 = 0
                else:
                    jong1 = jung2
                hangul = chr(((_CHO_HASH[cho] * 21) + _JUNG_HASH[jung1]) * 28
                             + _JONG_HASH[jong1] + _HANGUL_OFFSET)
            elif step == 4:
                jong2 = ord(array[complete_index + step])
                joined = _is_jong_joinable(jong1, jong2)
                jong1 = joined if joined else jong2
                hangul = chr(((_CHO_HASH[cho] * 21) + _JUNG_HASH[jung1]) * 28
                             + _JONG_HASH[jong1] + _HANGUL_OFFSET)
            elif step == 5:
                jong2 = ord(array[complete_index + step])
                jong1 = _is_jong_joinable(jong1, jong2)
                hangul = chr(((_CHO_HASH[cho] * 21) + _JUNG_HASH[jung1]) * 28
                             + _JONG_HASH[jong1] + _HANGUL_OFFSET)
            else:  # pragma: no cover - hangul-js loops forever past step 5
                result.append(hangul)
                complete_index = index
                return

            if complete_index + step >= index:
                result.append(hangul)
                complete_index = index
                return
            step += 1

    for i in range(length):
        code = ord(array[i])
        if not _is_cho(code) and not _is_jung(code) and not _is_jong(code):
            make_hangul(i - 1)
            make_hangul(i)
            stage = 0
            continue
        if stage == 0:
            if _is_cho(code):
                stage = 1
            elif _is_jung(code):
                stage = 4
        elif stage == 1:
            if _is_jung(code):
                stage = 2
            else:
                if _is_jong_joinable(previous_code, code):
                    stage = 5
                else:
                    make_hangul(i - 1)
        elif stage == 2:
            if _is_jong(code):
                stage = 3
            elif _is_jung(code):
                if not _is_jung_joinable(previous_code, code):
                    make_hangul(i - 1)
                    stage = 4
            else:
                make_hangul(i - 1)
                stage = 1
        elif stage == 3:
            if _is_jong(code):
                if not jong_joined and _is_jong_joinable(previous_code, code):
                    jong_joined = True
                else:
                    make_hangul(i - 1)
                    stage = 1
            elif _is_cho(code):
                make_hangul(i - 1)
                stage = 1
            elif _is_jung(code):
                make_hangul(i - 2)
                stage = 2
        elif stage == 4:
            if _is_jung(code):
                if _is_jung_joinable(previous_code, code):
                    make_hangul(i)
                    stage = 0
                else:
                    make_hangul(i - 1)
            else:
                make_hangul(i - 1)
                stage = 1
        elif stage == 5:
            if _is_jung(code):
                make_hangul(i - 2)
                stage = 2
            else:
                make_hangul(i - 1)
                stage = 1
        previous_code = code
    make_hangul(length - 1)
    return ''.join(result)


def is_hangul_syllable(ch):
    """True for U+AC00-U+D7A3 precomposed syllables."""
    return _is_hangul(ord(ch))


def contains_hangul(text):
    """True if text contains any Hangul syllable or jamo."""
    for ch in text:
        code = ord(ch)
        if _is_hangul(code) or _is_consonant(code) or _is_jung(code):
            return True
    return False
