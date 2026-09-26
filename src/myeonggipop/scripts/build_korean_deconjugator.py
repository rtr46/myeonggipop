"""
build_korean_deconjugator.py

Converts Yomitan's Korean deinflection rules
(yomitan/ext/js/language/ko/korean-transforms.js) into myeonggipop's
deconjugator.json rule format.

Mapping (semantics verified against
yomitan/ext/js/language/language-transformer.js):

  suffixInflection(inflected, deinflected, conditionsIn, conditionsOut)

  - Yomitan applies a rule to fresh text always; to an already-transformed
    text only if its condition set overlaps conditionsIn. The result carries
    conditionsOut.
  - myeonggipop tracks a single tag stack (Form.tags) where only the last tag
    is matched. A multi-condition Yomitan step is therefore expanded into
    one myeonggipop rule per (conditionIn, conditionOut) pair:
      * empty conditionsIn  -> 'onlyfinalrule' (fresh text only),
        pushing one conditionOut tag.
      * non-empty conditionsIn -> 'neverfinalrule' (chained text only),
        requiring con_tag and pushing dec_tag.
  - Rules sharing (type, detail, con_end) are merged into a single dict
    with parallel dec_end / con_tag / dec_tag lists, which myeonggipop zips
    positionally. This keeps the 2682 Yomitan rules compact.

Usage:
    python build_korean_deconjugator.py path/to/korean-transforms.js
        [-o deconjugator_ko.json]

The Yomitan rules operate on disassembled Hangul jamo (see
myeonggipop/dictionary/hangul.py); the generated file therefore contains
jamo-level endings and must be used together with jamo
pre/post-processing in lookup.
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict

RULE_RE = re.compile(
    r"suffixInflection\('([^']*)', '([^']*)', \[([^\]]*)\], \[([^\]]*)\]\)"
)
TRANSFORM_RE = re.compile(r"^        '([^']+)': \{$")
NAME_RE = re.compile(r"^            name: '([^']+)'")
UNEXPECTED_RE = re.compile(r"(prefixInflection|wholeWordInflection)\(")


def parse_conditions(s):
    return re.findall(r"'([^']+)'", s)


def parse_transforms(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    rules = []  # (transform_id, name, inf, deinf, cond_in, cond_out)
    current_id = None
    current_name = None
    for lineno, line in enumerate(lines, 1):
        m = UNEXPECTED_RE.search(line)
        if m:
            raise ValueError(
                f"Unsupported rule type {m.group(1)} at {path}:{lineno}. "
                f"This converter only handles suffixInflection."
            )
        m = TRANSFORM_RE.match(line)
        if m:
            current_id = m.group(1)
            current_name = None
            continue
        m = NAME_RE.match(line)
        if m and current_id is not None:
            current_name = m.group(1)
            continue
        m = RULE_RE.search(line)
        if m:
            if current_id is None:
                raise ValueError(f"Rule outside transform block at {path}:{lineno}")
            inf, deinf, ins, outs = m.groups()
            rules.append((
                current_id,
                current_name or current_id,
                inf, deinf,
                parse_conditions(ins),
                parse_conditions(outs),
            ))
    return rules


def expand_rules(parsed):
    """Expand to myeonggipop rule dicts, merged by (type, detail, con_end)."""
    merged = OrderedDict()  # key -> dict with parallel lists
    order = []

    def get_bucket(rule_type, detail, con_end):
        key = (rule_type, detail, con_end)
        if key not in merged:
            merged[key] = {
                'type': rule_type,
                'con_end': con_end,
                'dec_end': [],
                'con_tag': [],
                'dec_tag': [],
                'detail': detail,
            }
            order.append(key)
        return merged[key]

    n_expanded = 0
    for tid, name, inf, deinf, cond_in, cond_out in parsed:
        if not inf:
            # Degenerate upstream quirk, e.g. suffixInflection('', '다', [], ['ida'])
            # in '-로라': Yomitan's /$/ regex matches *any* text and its
            # deinflect() collapses everything to just the deinflected suffix.
            # myeonggipop rules cannot express "whole text -> X", and the only
            # such candidate ('다') is not a useful dictionary headword, so
            # these rules are skipped (counted in main()).
            continue
        outs = cond_out if cond_out else [None]
        if not cond_in:
            for cout in outs:
                b = get_bucket('onlyfinalrule', name, inf)
                b['dec_end'].append(deinf)
                b['con_tag'].append(None)
                b['dec_tag'].append(cout)
                n_expanded += 1
        else:
            for cin in cond_in:
                for cout in outs:
                    b = get_bucket('neverfinalrule', name, inf)
                    b['dec_end'].append(deinf)
                    b['con_tag'].append(cin)
                    b['dec_tag'].append(cout)
                    n_expanded += 1

    result = []
    for key in order:
        b = merged[key]
        # Drop all-None con_tag (starter rules need no tag matching and
        # read cleaner without it).
        if all(t is None for t in b['con_tag']):
            del b['con_tag']
        # Collapse single-element lists to scalars (matches existing file style).
        for field in ('dec_end', 'con_tag', 'dec_tag'):
            if field in b and len(b[field]) == 1:
                b[field] = b[field][0]
        result.append(b)
    return result, n_expanded


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Convert Yomitan Korean transforms to myeonggipop deconjugator rules')
    parser.add_argument('yomitan_js',
                        help='Path to yomitan korean-transforms.js')
    parser.add_argument('-o', '--output',
                        default=os.path.join(os.path.dirname(__file__),
                                             'deconjugator_ko.json'),
                        help='Output path (default: scripts/deconjugator_ko.json)')
    args = parser.parse_args(argv)

    if not os.path.isfile(args.yomitan_js):
        print(f"ERROR: File not found: {args.yomitan_js}", file=sys.stderr)
        sys.exit(1)

    parsed = parse_transforms(args.yomitan_js)
    print(f"Parsed {len(parsed)} Yomitan suffix rules")
    if not parsed:
        print("ERROR: no rules parsed; is this korean-transforms.js?", file=sys.stderr)
        sys.exit(1)

    rules, n_expanded = expand_rules(parsed)
    print(f"Expanded to {n_expanded} myeonggipop variants in {len(rules)} grouped rules")
    skipped = sum(1 for r in parsed if not r[2])
    if skipped:
        print(f"Skipped {skipped} degenerate empty-suffix rule(s) (see expand_rules)")

    payload = [
        "Korean deinflection rules converted from Yomitan's korean-transforms.js.",
        "Rule endings are disassembled Hangul jamo; use with jamo pre/post-processing.",
        "Source: https://github.com/yomidevs/yomitan (GPL-3.0).",
        *rules,
    ]
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write('\n')
    size_kb = os.path.getsize(args.output) / 1024
    print(f"Wrote {args.output} ({size_kb:.0f} KB)")


if __name__ == '__main__':
    main()
