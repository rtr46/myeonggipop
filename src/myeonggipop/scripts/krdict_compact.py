# krdict_compact.py
"""
Compact gloss extraction for Lyroxide-style KRDICT Yomitan dictionaries.

A KRDICT EN definition has this shape (verified against KO-EN.KRDICT,
both the full and the No.Examples builds):

    {"type": "structured-content", "content": [
        {"tag": "span", ...},          # headword echo ("고양이", "학 〔鶴〕"):
                                       # text dropped (popup header shows it),
                                       # Hanja harvested
        {"tag": "div", ...},           # one meaning block per sense group:
                                       # children alternate short-gloss divs
                                       # (contain spans, e.g. "cat", "1. -go")
                                       # and verbose bare-string divs
                                       # (e.g. "A small animal ...")
        {"tag": "details", ...},       # examples ("See More")  <- dropped
        "→ 물고",                      # bare strings: cross-references <- kept
    ]}

``krdict_meaning_pairs`` returns ``(pairs, headword_hanja)`` where pairs is
a list of ``(short_node, [verbose_nodes])``. It returns ``(None, [])`` when
the definition does not have the KRDICT shape — callers must then fall back
to their regular full rendering so no data is lost for other dictionaries.

The fingerprint is a ``details`` block with a "See More" summary (full
KRDICT builds) or, failing that, any ``lang`` attribute in the tree
(present in all Lyroxide KRDICT builds including No.Examples, whose
builder tags every node). JMdict-based dictionaries set neither.
"""

import re

SEE_MORE_SUMMARY = 'See More'

HANJA_RE = re.compile(r'〔([^〕]+)〕')


def split_hanja(text: str) -> tuple:
    """
    Split 〔漢字〕 spans out of a gloss string.
    Returns (clean_text, [hanja, ...]). Never returns empty clean text.
    """
    hanja = HANJA_RE.findall(text or '')
    clean = re.sub(r'\s+', ' ', HANJA_RE.sub('', text or '')).strip()
    if not clean:
        clean = re.sub(r'\s+', ' ', text or '').strip()
    return clean, hanja


def _flatten(node) -> str:
    """Plain-text rendering used for fingerprinting and text output."""
    if node is None:
        return ''
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return ''.join(_flatten(child) for child in node)
    if isinstance(node, dict):
        tag = node.get('tag', '')
        if tag in ('rt', 'rp'):
            return ''
        if tag == 'ruby':
            content = node.get('content')
            if isinstance(content, list):
                for child in content:
                    if isinstance(child, dict) and child.get('tag') != 'rt':
                        return _flatten(child)
            return _flatten(content)
        inner = _flatten(node.get('content'))
        if tag in ('div', 'li', 'tr', 'br'):
            return inner + ' '
        return inner
    return ''


def _contains_see_more(node) -> bool:
    """True if any ``details`` subtree has a "See More" summary."""
    if isinstance(node, list):
        return any(_contains_see_more(child) for child in node)
    if isinstance(node, dict):
        if node.get('tag') == 'details':
            for child in (node.get('content') or []):
                if (isinstance(child, dict) and child.get('tag') == 'summary'
                        and _flatten(child).strip() == SEE_MORE_SUMMARY):
                    return True
        return _contains_see_more(node.get('content'))
    return False


def _contains_lang_attr(node) -> bool:
    """True if any node carries a ``lang`` attribute (Lyroxide builder habit)."""
    if isinstance(node, list):
        return any(_contains_lang_attr(child) for child in node)
    if isinstance(node, dict):
        if 'lang' in node:
            return True
        return _contains_lang_attr(node.get('content'))
    return False


def is_krdict_definition(defn) -> bool:
    """Fingerprint check for Lyroxide KRDICT structured-content definitions."""
    return (isinstance(defn, dict)
            and defn.get('type') == 'structured-content'
            and (_contains_see_more(defn.get('content'))
                 or _contains_lang_attr(defn.get('content'))))


def _has_direct_span(content) -> bool:
    """True if a div's direct children include a span (short-gloss marker)."""
    return (isinstance(content, list)
            and any(isinstance(c, dict) and c.get('tag') == 'span'
                    for c in content))


def _is_pattern_badge(content) -> bool:
    """
    True for sentence-pattern notation divs such as
    [badge-span "Sentence", span "1이 먹다"]. These carry a gray
    backgroundColor badge span and are neither translations nor
    explanations, so they are skipped.
    """
    if not isinstance(content, list):
        return False
    for child in content:
        if not isinstance(child, dict) or child.get('tag') != 'span':
            continue
        style = child.get('style')
        if isinstance(style, dict) and 'backgroundColor' in style:
            return True
    return False


def krdict_meaning_pairs(content):
    """
    Split KRDICT definition content into (short_node, [verbose_nodes]) pairs
    plus headword-span Hanja. Returns (None, []) when nothing KRDICT-shaped
    was found.
    """
    if not isinstance(content, list):
        return None, []
    pairs = []
    headword_hanja = []
    for block in content:
        if isinstance(block, str):
            if block.strip():
                pairs.append((block, []))
            continue
        if not isinstance(block, dict):
            continue
        tag = block.get('tag')
        if tag == 'details':
            continue  # examples
        if tag == 'span':
            # headword echo: harvest Hanja, drop the text
            headword_hanja.extend(HANJA_RE.findall(_flatten(block)))
            continue
        if tag != 'div':
            continue
        inner = block.get('content')
        if not isinstance(inner, list) or not inner:
            continue
        if _is_pattern_badge(inner):
            continue
        if inner and isinstance(inner[0], dict) and inner[0].get('tag') == 'div':
            # meaning block: alternate short-gloss / verbose children
            current = None
            for child in inner:
                if isinstance(child, dict) and child.get('tag') == 'details':
                    continue
                if (isinstance(child, dict) and child.get('tag') == 'div'
                        and _has_direct_span(child.get('content'))
                        and not _is_pattern_badge(child.get('content'))):
                    current = [child, []]
                    pairs.append(current)
                elif current is not None:
                    # verbose div (bare string) or stray string: attach.
                    # Pattern-badge divs ("Sentence ...") are skipped here too.
                    if isinstance(child, str):
                        if child.strip():
                            current[1].append(child)
                    elif (isinstance(child, dict) and child.get('tag') == 'div'
                          and not _is_pattern_badge(child.get('content'))):
                        current[1].append(child)
            # a meaning block with no recognizable pairs contributes nothing
    return (pairs, headword_hanja) if pairs else (None, [])
