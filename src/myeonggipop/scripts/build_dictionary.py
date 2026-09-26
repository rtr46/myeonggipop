"""
build_dictionary.py
Builds dictionary.pkl from scratch for myeonggipop.

Downloads the pinned Lyroxide KRDICT Yomitan dictionaries (Korean Basic
Dictionary data by the National Institute of Korean Language,
CC BY-SA 2.0 KR) and runs them through the same import pipeline as
`myeonggipop import-yomitan-dict-text`, so a manual import and this build
produce identical dictionaries.

No frequency data is used: KRDICT level stars (e.g. Noun ⭐⭐⭐ in the
entry tags) carry the frequency signal instead, and every entry keeps the
default rank.

Provenance (titles, authors, license notes) is recorded in the pickle
payload under 'sources'.
"""

import argparse
import io
import json
import os
import pickle
import sys
import time
import zipfile
from collections import defaultdict

import requests

from myeonggipop.scripts.import_yomitan_dict_text import build_from_zip
from myeonggipop.utils.paths import paths, DECONJUGATOR_FILENAME

CACHE_DIR = paths.cache_dir
DEFAULT_OUTPUT = paths.dictionary_path

RELEASES_API = "https://api.github.com/repos/Lyroxide/yomitan-ko-dic/releases/tags/{tag}"
DEFAULT_RELEASE_TAG = "1.0.0"
DEFAULT_LANG = "EN"

# Glossary languages shipped by the KRDICT release (plus KR monolingual).
KNOWN_LANGS = ["EN", "ES", "FR", "JA", "ZH", "TH", "VI", "RU", "AR", "MN",
               "ID", "KR"]


def ensure_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)


def discover_assets(tag: str) -> dict:
    """Map release asset names to download URLs via the GitHub API."""
    url = RELEASES_API.format(tag=tag)
    print(f"  Querying {url} ...")
    response = requests.get(url, timeout=60,
                            headers={'Accept': 'application/vnd.github+json'})
    response.raise_for_status()
    return {a['name']: a['browser_download_url']
            for a in response.json().get('assets', [])}


def pick_asset(assets: dict, lang: str, no_examples: bool) -> tuple:
    """Pick the KRDICT asset for a glossary language, e.g. KO-EN.KRDICT.zip."""
    wanted = f"KO-{lang.upper()}.KRDICT"
    wanted += ".No.Examples.zip" if no_examples else ".zip"
    if wanted in assets:
        return wanted, assets[wanted]
    print(f"ERROR: asset '{wanted}' not found in this release.",
          file=sys.stderr)
    print("Available KRDICT assets:", file=sys.stderr)
    for name in sorted(n for n in assets if 'KRDICT' in n):
        print(f"  {name}", file=sys.stderr)
    sys.exit(1)


def load_or_download(name: str, url: str) -> bytes:
    """Fetch a release asset, caching it in the user cache directory."""
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path):
        print(f"  Using cached: {path}")
        with open(path, 'rb') as f:
            return f.read()
    print(f"  Downloading {name} ...")
    with requests.get(url, timeout=300, stream=True) as response:
        response.raise_for_status()
        data = response.content
    with open(path, 'wb') as f:
        f.write(data)
    print(f"  Saved {len(data) // 1024} KB to {path}")
    return data


def load_korean_rules() -> list:
    path = os.path.join(os.path.dirname(__file__), DECONJUGATOR_FILENAME)
    if not os.path.exists(path):
        print(f"ERROR: {path} not found.", file=sys.stderr)
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        rules = [r for r in json.load(f) if isinstance(r, dict)]
    print(f"  {len(rules)} Korean deconjugator rules loaded")
    return rules


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Build myeonggipop dictionary.pkl from KRDICT data')
    parser.add_argument('--lang', default=DEFAULT_LANG,
                        help=f'Glossary language, e.g. {", ".join(KNOWN_LANGS)} '
                             f'(default: {DEFAULT_LANG})')
    parser.add_argument('--no-examples', action='store_true',
                        help='Use the smaller No.Examples dictionary build')
    parser.add_argument('--release-tag', default=DEFAULT_RELEASE_TAG,
                        help=f'Pinned upstream release (default: {DEFAULT_RELEASE_TAG})')
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT,
                        help=f'Output pickle path (default: {DEFAULT_OUTPUT})')
    args = parser.parse_args(argv)

    ensure_dirs()

    print("\n[1/3] Resolving KRDICT download ...")
    assets = discover_assets(args.release_tag)
    asset_name, asset_url = pick_asset(assets, args.lang, args.no_examples)
    print(f"  Selected: {asset_name}")

    print("\n[2/3] Importing ...")
    t0 = time.time()
    data = load_or_download(asset_name, asset_url)
    deconjugator_rules = load_korean_rules()

    all_entries: dict = {}
    all_lookup_map: dict = defaultdict(list)
    sources: list = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sequenced = True
        if 'index.json' in zf.namelist():
            with zf.open('index.json') as f:
                idx = json.load(f)
            print(f"    Title:    {idx.get('title', '(unknown)')}")
            print(f"    Revision: {idx.get('revision', '(unknown)')}")
            print(f"    Author:   {idx.get('author', '(unknown)')}")
            if idx.get('attribution'):
                # Attribution is Korean text; may not fit the console encoding.
                print(f"    License:  {idx.get('attribution')}".encode(
                    'ascii', 'backslashreplace').decode('ascii'))
            sequenced = idx.get('sequenced', True)
            sources.append({
                'file': asset_name,
                'title': idx.get('title'),
                'revision': idx.get('revision'),
                'author': idx.get('author'),
                'url': idx.get('url'),
                'attribution': idx.get('attribution'),
            })
        entries, lookup_additions = build_from_zip(
            zf, dict_index=0, freq_override={}, sequenced=sequenced)
    all_entries.update(entries)
    for surface, me_list in lookup_additions.items():
        all_lookup_map[surface].extend(me_list)
    print(f"    Done in {time.time() - t0:.1f}s")

    print(f"\n[3/3] Saving dictionary to {args.output} ...")
    t0 = time.time()
    payload = {
        'entries': all_entries,
        'lookup_map': dict(all_lookup_map),
        'kanji_entries': {},
        'deconjugator_rules': deconjugator_rules,
        'sources': sources,
    }
    with open(args.output, 'wb') as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    size_mb = os.path.getsize(args.output) / 1_048_576
    print(f"  Saved {size_mb:.1f} MB in {time.time() - t0:.1f}s")
    print("\nBuild complete.")


if __name__ == '__main__':
    main()
