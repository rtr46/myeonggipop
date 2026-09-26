"""
import_yomitan_dict_text.py
Imports one or more Yomitan/Yomichan dictionary zip files and produces a
dictionary.pkl in the same format as build_dictionary.py.

Usage:
    python import_yomitan_dict.py dict1.zip [dict2.zip ...] [-o output.pkl]

Multiple zips are merged into one pickle.  Entry IDs are namespaced by
dictionary index to avoid collisions.

Structured-content definitions are flattened to raw text at import time
"""

import argparse
import json
import os
import pickle
import re
import sys
import time
import zipfile
from collections import defaultdict
from typing import Optional

from myeonggipop.scripts.krdict_compact import (
    is_krdict_definition, krdict_meaning_pairs, split_hanja)
from myeonggipop.utils.paths import paths, DECONJUGATOR_FILENAME

DATA_DIR = 'data'
DEFAULT_OUTPUT = paths.dictionary_path
DEFAULT_FREQ = 999_999

# Each dictionary's entry IDs start at this multiple of its index (0-based).
# Allows up to 10 million entries per dictionary before collision.
ID_NAMESPACE = 10_000_000


# ── Structured-content text extraction ────────────────────────────────────────

def extract_text(node) -> str:
    """
    Recursively extract plain text from a structured-content node.
    Loses all formatting but preserves meaning for popup display.
    Inserts a space between block-level tags (div, li, tr) for readability.
    """
    if node is None:
        return ''
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return ''.join(extract_text(child) for child in node)
    if isinstance(node, dict):
        tag = node.get('tag', '')
        content = node.get('content')
        # For ruby tags: show rb text only (skip rt pronunciation guides)
        if tag == 'ruby':
            if isinstance(content, list):
                for child in content:
                    if isinstance(child, dict) and child.get('tag') != 'rt':
                        return extract_text(child)
            return extract_text(content)
        if tag == 'rt':
            return ''
        inner = extract_text(content)
        # Add spacing around block elements
        if tag in ('div', 'li', 'tr', 'br'):
            return inner + ' '
        return inner
    return ''


def _clean(text: str) -> str:
    """Strip and collapse runs of whitespace."""
    return re.sub(r'\s+', ' ', (text or '').strip())


def extract_rich_glosses(definitions: list) -> tuple:
    """
    Convert a yomitan definitions array into (glosses, verbose, hanja).

    - glosses: short translations, one per meaning ("cat", "1. -go").
    - verbose: verbose explanations parallel to glosses (possibly '');
      only KRDICT definitions provide these.
    - hanja: union of 〔漢字〕 spans found (headword echo included);
      stripped from both texts above.
    Handles plain strings, {type:text}, {type:structured-content}, and
    ignores image-only and deinflection entries.
    """
    glosses, verbose, hanja = [], [], []

    def add(text, verb=''):
        text, hj = split_hanja(_clean(text))
        if not text:
            return
        verb, vhj = split_hanja(_clean(verb))
        for h in list(hj) + list(vhj):
            if h not in hanja:
                hanja.append(h)
        glosses.append(text)
        verbose.append(verb)

    for defn in definitions:
        if isinstance(defn, str):
            add(defn)
        elif isinstance(defn, dict):
            t = defn.get('type')
            if t == 'text':
                add(defn.get('text', ''))
            elif t == 'structured-content':
                content = defn.get('content')
                if is_krdict_definition(defn):
                    pairs, hw_hanja = krdict_meaning_pairs(content)
                    if pairs is not None:
                        for h in hw_hanja:
                            if h not in hanja:
                                hanja.append(h)
                        for short_node, verbose_nodes in pairs:
                            verb = ' '.join(
                                _clean(extract_text(vn)) for vn in verbose_nodes)
                            add(extract_text(short_node), verb)
                        continue
                add(extract_text(content))
            # type == 'image' or deinflection arrays: skip
        elif isinstance(defn, list):
            # Deinflection entry [uninflected_term, [rules]] — skip
            pass
    return glosses, verbose, hanja


# ── Frequency parsing ──────────────────────────────────────────────────────────

def parse_freq_value(freq_data) -> Optional[int]:
    """
    Extract a numeric frequency rank from a yomitan freq meta value.
    Returns None if the value cannot be interpreted as a rank.
    """
    if isinstance(freq_data, (int, float)):
        return int(freq_data)
    if isinstance(freq_data, str):
        try:
            return int(freq_data)
        except ValueError:
            return None
    if isinstance(freq_data, dict):
        # {value: N, displayValue: "..."} — direct rank
        if 'value' in freq_data:
            return int(freq_data['value'])
        # {reading: "...", frequency: ...} — nested
        inner = freq_data.get('frequency')
        if inner is not None:
            return parse_freq_value(inner)
    return None


def load_freq_map_from_zip(zf: zipfile.ZipFile) -> dict:
    """
    Read all term_meta_bank_*.json files from an open zip and build:
      {(term, reading_or_empty): freq_rank}
    When reading is absent from the meta entry, key reading is ''.
    Takes the minimum (best) rank seen for each key.
    """
    freq: dict = {}
    for name in sorted(zf.namelist()):
        if not re.match(r'term_meta_bank_\d+\.json', os.path.basename(name)):
            continue
        with zf.open(name) as f:
            rows = json.load(f)
        for row in rows:
            if len(row) < 3 or row[1] != 'freq':
                continue
            term = row[0]
            raw = row[2]
            reading = ''
            if isinstance(raw, dict) and 'reading' in raw:
                reading = raw['reading']
                rank_val = parse_freq_value(raw.get('frequency'))
            else:
                rank_val = parse_freq_value(raw)
            if rank_val is None:
                continue
            key = (term, reading)
            if key not in freq or rank_val < freq[key]:
                freq[key] = rank_val
    return freq


# ── Term bank loading ──────────────────────────────────────────────────────────

def load_term_banks_from_zip(zf: zipfile.ZipFile) -> list:
    """Return all rows from term_bank_*.json, preserving order."""
    rows = []
    for name in sorted(zf.namelist()):
        if not re.match(r'term_bank_\d+\.json', os.path.basename(name)):
            continue
        with zf.open(name) as f:
            rows.extend(json.load(f))
    return rows


# ── Building the internal structures ──────────────────────────────────────────

def build_from_zip(zf: zipfile.ZipFile, dict_index: int, freq_override: dict,
                   sequenced: bool = True) -> tuple:
    """
    Process one zip file and return (entries, lookup_map_additions).

    entries: {entry_id: [sense, ...]}
    lookup_map_additions: {surface: [(written_form, reading, freq, entry_id), ...]}

    dict_index is used to namespace entry IDs: entry_id = dict_index * ID_NAMESPACE + sequence
    freq_override allows the caller to pass in a pre-merged frequency map.
    sequenced=False (from the zip's index.json) means rows carry no usable
    sequence numbers, so every row becomes its own entry.
    """
    freq_map = load_freq_map_from_zip(zf)
    # Merge with any externally provided overrides (unused in standalone mode,
    # kept for future additive use)
    for k, v in freq_override.items():
        if k not in freq_map or v < freq_map[k]:
            freq_map[k] = v

    rows = load_term_banks_from_zip(zf)
    print(f"    {len(rows)} term rows loaded")

    # Group rows by sequence number.
    # Rows with sequence 0 are treated as standalone (no grouping).
    # For sequence > 0, all rows sharing a sequence form one entry.
    # Within a sequence, we use the first term+reading pair seen as the
    # canonical display form.
    # Dictionaries with "sequenced": false in index.json (e.g. KRDICT builds)
    # have no usable sequence column: every row is standalone.
    seq_groups: dict[int, list] = defaultdict(list)
    standalone_counter = -1  # negative IDs for sequence-0 rows before namespacing
    for row in rows:
        if len(row) < 6:
            continue
        seq = row[6] if (sequenced and len(row) > 6) else 0
        if seq == 0:
            # Each row is its own entry; give it a unique synthetic sequence
            seq_groups[standalone_counter].append(row)
            standalone_counter -= 1
        else:
            seq_groups[seq].append(row)

    entries = {}
    lookup_map = defaultdict(list)
    id_base = dict_index * ID_NAMESPACE

    for seq, group_rows in seq_groups.items():
        # Namespace the ID
        if seq < 0:
            # Standalone row: use id_base + offset from negative counter
            entry_id = id_base + (ID_NAMESPACE + seq)  # e.g. id_base + 9999999, 9999998, ...
        else:
            entry_id = id_base + seq

        # Determine canonical term and reading from the first row
        first_row = group_rows[0]
        canon_term = first_row[0] or ''
        canon_read = first_row[1] or ''  # empty string when the term has no separate reading

        # Build senses from all rows in this group
        senses = []
        for row in group_rows:
            term = row[0] or ''
            reading = row[1] or ''
            # Yomitan banks may contain nulls; coerce to empty strings/lists
            def_tags_str = row[2] if len(row) > 2 and row[2] else ''
            rules_str = row[3] if len(row) > 3 and row[3] else ''
            definitions = row[5] if len(row) > 5 and row[5] else []
            term_tags_str = row[7] if len(row) > 7 and row[7] else ''

            glosses, verbose, hanja = extract_rich_glosses(definitions)
            if not glosses:
                continue

            # Merge definition_tags and term_tags into our 'tags' field
            all_tag_strings = (def_tags_str + ' ' + term_tags_str).split()
            tags = [t for t in all_tag_strings if t]

            # rules field (v1, v5k, adj-i ...) maps to pos
            pos = [r for r in rules_str.split() if r]

            senses.append({'glosses': glosses, 'verbose': verbose,
                           'hanja': hanja, 'pos': pos, 'tags': tags})

        if not senses:
            continue

        entries[entry_id] = senses

        # Frequency lookup: try (term, reading) then (term, '') as fallback
        def get_freq(term: str, reading: str) -> int:
            return freq_map.get((term, reading),
                                freq_map.get((term, ''), DEFAULT_FREQ))

        # ── lookup_map entries ─────────────────────────────────────────────
        # Collect all unique (term, reading) pairs across this group's rows.
        # Each unique CJK-containing term surface gets one term-path entry;
        # each unique reading surface gets one reading-path entry.
        seen_terms: set = set()
        seen_reading_surfaces: set = set()

        for row in group_rows:
            term = row[0] or ''
            reading = row[1] or ''  # '' means reading-less

            # Term-path: term contains CJK (e.g. Hanja) characters
            if _has_cjk(term) and term not in seen_terms:
                seen_terms.add(term)
                display_read = reading if reading else canon_read
                freq = get_freq(term, display_read)
                lookup_map[term].append((canon_term, display_read, freq, entry_id))

            # Reading-path
            surface_reading = reading if reading else term
            if surface_reading not in seen_reading_surfaces:
                seen_reading_surfaces.add(surface_reading)
                if reading:
                    # Has a separate written form
                    freq = get_freq(surface_reading, reading)
                    lookup_map[surface_reading].append((canon_term, reading, freq, entry_id))
                else:
                    # Reading-less entry: written_form == surface, no separate reading
                    freq = get_freq(term, '')
                    lookup_map[term].append((term, None, freq, entry_id))

    n_refs = sum(len(v) for v in lookup_map.values())
    print(f"    {len(entries)} entries | {n_refs} lookup refs")
    return entries, lookup_map


def _has_cjk(text: str) -> bool:
    return any(0x4E00 <= ord(c) <= 0x9FFF for c in text)


# ── Main ───────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Import Yomitan dictionary zip(s) into dictionary.pkl')
    parser.add_argument('zips', nargs='+', help='Path(s) to Yomitan .zip files')
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT,
                        help=f'Output pickle path (default: {DEFAULT_OUTPUT})')
    args = parser.parse_args(argv)

    # Load Korean deconjugator rules
    deconjugator_path = os.path.join(
        os.path.dirname(__file__), DECONJUGATOR_FILENAME)
    if not os.path.exists(deconjugator_path):
        print(f"ERROR: {deconjugator_path} not found. "
              f"Please ensure {DECONJUGATOR_FILENAME} is in the package scripts directory.", file=sys.stderr)
        sys.exit(1)
    with open(deconjugator_path, 'r', encoding='utf-8') as f:
        deconjugator_rules = [r for r in json.load(f) if isinstance(r, dict)]
    print(f"Loaded {len(deconjugator_rules)} Korean deconjugator rules")

    all_entries: dict = {}
    all_lookup_map: dict = defaultdict(list)

    for i, zip_path in enumerate(args.zips):
        if not os.path.isfile(zip_path):
            print(f"ERROR: File not found: {zip_path}", file=sys.stderr)
            sys.exit(1)

        print(f"\n[{i + 1}/{len(args.zips)}] Importing {os.path.basename(zip_path)} ...")
        t0 = time.time()

        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Print dictionary metadata if available
            sequenced = True
            if 'index.json' in zf.namelist():
                with zf.open('index.json') as f:
                    idx = json.load(f)
                print(f"    Title:    {idx.get('title', '(unknown)')}")
                print(f"    Revision: {idx.get('revision', '(unknown)')}")
                print(f"    Author:   {idx.get('author', '(unknown)')}")
                sequenced = idx.get('sequenced', True)
                if not sequenced:
                    print("    Unsequenced dictionary: each row becomes its own entry")

            entries, lookup_additions = build_from_zip(
                zf, dict_index=i, freq_override={}, sequenced=sequenced)

        # Merge into combined structures
        # On entry_id collision (same sequence across different dicts), last writer wins.
        all_entries.update(entries)
        for surface, me_list in lookup_additions.items():
            all_lookup_map[surface].extend(me_list)

        print(f"    Done in {time.time() - t0:.1f}s")

    print(f"\nTotal: {len(all_entries)} entries, "
          f"{sum(len(v) for v in all_lookup_map.values())} lookup refs")

    print(f"\nSaving to {args.output} ...")
    t0 = time.time()
    payload = {
        'entries': all_entries,
        'lookup_map': dict(all_lookup_map),
        'kanji_entries': {},  # not produced by yomitan import
        'deconjugator_rules': deconjugator_rules,
    }
    with open(args.output, 'wb') as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    size_mb = os.path.getsize(args.output) / 1_048_576
    print(f"Saved {size_mb:.1f} MB in {time.time() - t0:.1f}s")
    print("\nImport complete.")


if __name__ == '__main__':
    main()
