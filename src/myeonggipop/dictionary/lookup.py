# lookup.py
import logging
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from myeonggipop.config.config import config, MAX_DICT_ENTRIES, DICT_PATH
from myeonggipop.dictionary.customdict import Dictionary, WRITTEN_FORM_INDEX, READING_INDEX, FREQUENCY_INDEX, \
    ENTRY_ID_INDEX, DEFAULT_FREQ
from myeonggipop.dictionary.deconjugator import Deconjugator, Form
from myeonggipop.dictionary.hangul import disassemble_to_string, assemble

# Korean uses Western-style punctuation (plus CJK brackets for mixed text).
# Spaces separate eojeol, so ' ' is deliberately NOT a separator here:
# lookup continues across the space and prefix scanning handles the rest.
SEPARATORS = {
    "。", "「", "」", "『", "』", "〈", "〉", "《", "》", "：", "・", "／",
    "…", "‥", "？", "！", ".", ",", "!", "?", "~", "·", "—", "–",
    "\"", "'", "“", "”", "‘", "’", "(", ")", "[", "]",
}

logger = logging.getLogger(__name__)


def star_count(tags) -> int:
    """Number of KRDICT level stars (⭐) across tag strings."""
    return sum(str(t).count('⭐') for t in (tags or []))


def sort_senses_by_stars(senses: list) -> list:
    """
    Sort senses by descending star count (stable: equal stars keep their
    encounter order). Ensures e.g. 3-star senses surface before unstarred
    ones and survive the per-entry sense cap.
    """
    return sorted(senses, key=lambda s: star_count(s.get('tags', [])),
                  reverse=True)


@dataclass
class DictionaryEntry:
    id: int
    written_form: str
    reading: str  # rarely used for Korean (KRDICT has no readings)
    senses: list
    freq: int
    deconjugation_process: tuple
    priority: float = 0.0


class Lookup(threading.Thread):
    def __init__(self, shared_state, popup_window):
        super().__init__(daemon=True, name="Lookup")
        self.shared_state = shared_state
        self.popup_window = popup_window
        self.last_hit_result = None

        self.dictionary = Dictionary()
        self.lookup_cache: OrderedDict = OrderedDict()
        self.CACHE_SIZE = 500

        if not self.dictionary.load_dictionary(DICT_PATH):
            raise RuntimeError("Failed to load dictionary.")
        self.deconjugator = Deconjugator(self.dictionary.deconjugator_rules)

    def clear_cache(self):
        self.lookup_cache = OrderedDict()

    def run(self):
        logger.debug("Lookup thread started.")
        while self.shared_state.running:
            try:
                hit_result = self.shared_state.lookup_queue.get()
                if not self.shared_state.running: break
                logger.debug("Lookup: Triggered")

                # skip lookup if hit_result didnt change
                if hit_result == self.last_hit_result:
                    continue
                self.last_hit_result = hit_result

                lookup_result = self.lookup(self.last_hit_result) if self.last_hit_result else None
                self.popup_window.set_latest_data(lookup_result)
            except:
                logger.exception("An unexpected error occurred in the lookup loop. Continuing...")
        logger.debug("Lookup thread stopped.")

    def lookup(self, lookup_string: str) -> List:
        if not lookup_string:
            return []
        logger.info(f"Looking up: {lookup_string}")  # keep at info level so people know whats up

        text = lookup_string.strip()
        text = text[:config.max_lookup_length]
        for i, ch in enumerate(text):
            if ch in SEPARATORS:
                text = text[:i]
                break
        if not text:
            return []

        if text in self.lookup_cache:
            self.lookup_cache.move_to_end(text)
            return self.lookup_cache[text]

        results = self._do_lookup(text)

        self.lookup_cache[text] = results
        if len(self.lookup_cache) > self.CACHE_SIZE:
            self.lookup_cache.popitem(last=False)
        return results

    def _do_lookup(self, text: str) -> List[DictionaryEntry]:
        """
        Scan all prefixes of `text` (longest first), deconjugate each, then
        look up every resulting form in the dictionary map.

        Korean rules operate on disassembled jamo (same as Yomitan's Hangul
        preprocessing); each candidate is reassembled before the dictionary
        lookup (Yomitan's postprocessing).

        Collected results are keyed by entry id. The final list is sorted
        by (match_length DESC, priority DESC, written length DESC).
        """
        # entry_id -> (map_entry, form, match_len)
        collected: Dict[int, Tuple[tuple, Form, int]] = {}

        for prefix_len in range(len(text), 0, -1):
            prefix = text[:prefix_len]

            forms = self.deconjugator.deconjugate(disassemble_to_string(prefix))
            forms = {
                Form(text=assemble(form.text),
                     process=form.process, tags=form.tags)
                for form in forms
            }

            prefix_hits = []

            for form in forms:
                map_entries = self.dictionary.lookup_map.get(form.text, [])
                if not map_entries:
                    continue

                for map_entry in map_entries:
                    entry_id = map_entry[ENTRY_ID_INDEX]

                    # POS validation: if the deconjugator tagged this form,
                    # the entry must contain that part-of-speech. Entries
                    # without any POS info (common in imported dictionaries)
                    # cannot be validated and are kept.
                    if form.tags:
                        required_pos = form.tags[-1]
                        entry_senses = self.dictionary.entries.get(entry_id, [])
                        all_pos = {p for s in entry_senses for p in s['pos']}
                        if all_pos and required_pos not in all_pos:
                            logger.debug(
                                f"Pruning id={entry_id} ({map_entry[WRITTEN_FORM_INDEX]}): "
                                f"required POS '{required_pos}' not in {all_pos}"
                            )
                            continue

                    prefix_hits.append((map_entry, form))

            if prefix_hits:
                for map_entry, form in prefix_hits:
                    entry_id = map_entry[ENTRY_ID_INDEX]
                    if entry_id not in collected:
                        collected[entry_id] = (map_entry, form, prefix_len)

        return self._format_and_sort(list(collected.values()), text)

    def _format_and_sort(
            self,
            raw: List[Tuple[tuple, Form, int]],
            original_lookup: str,
    ) -> List[DictionaryEntry]:
        """
        Merge map entries that share (written_form, reading) across different
        deconjugation paths, compute priority, then sort and return DictionaryEntry list.
        """
        # Key: (written_form, reading)  Value: accumulated data dict
        merged: Dict[Tuple[str, str], dict] = {}

        for map_entry, form, match_len in raw:
            written = map_entry[WRITTEN_FORM_INDEX]
            reading = map_entry[READING_INDEX] or ''
            freq = map_entry[FREQUENCY_INDEX]
            entry_id = map_entry[ENTRY_ID_INDEX]

            entry_senses = self.dictionary.entries.get(entry_id, [])
            priority = self._calculate_priority(freq, form, match_len,
                                                entry_senses)

            key = (written, reading)
            if key not in merged:
                merged[key] = {
                    'id': entry_id,
                    'written_form': written,
                    'reading': reading,
                    'senses': list(entry_senses),
                    'freq': freq,
                    'deconjugation_process': form.process,
                    'priority': priority,
                    'match_len': match_len,
                }
            else:
                # Same (written_form, reading) reached via a different deconjugation path
                # or from a different entry ID (genuine homograph with identical display forms).
                # Merge senses from the other entry and keep the best freq/priority/match_len.
                cur = merged[key]
                if entry_id != cur['id']:
                    cur['senses'].extend(entry_senses)
                if priority > cur['priority']:
                    cur['priority'] = priority
                    cur['id'] = entry_id
                    cur['deconjugation_process'] = form.process
                if freq < cur['freq']:
                    cur['freq'] = freq
                if match_len > cur['match_len']:
                    cur['match_len'] = match_len

        sorted_entries = sorted(
            merged.values(),
            # match_len, then priority, then longer written forms first:
            # the last tie-break keeps e.g. 먹다 ahead of 먹 on equal scores
            # and makes ordering deterministic.
            key=lambda x: (x['match_len'], x['priority'],
                           len(x['written_form'] or '')),
            reverse=True,
        )

        results = []
        for d in sorted_entries[:MAX_DICT_ENTRIES]:
            results.append(DictionaryEntry(
                id=d['id'],
                written_form=d['written_form'],
                reading=d['reading'],
                senses=sort_senses_by_stars(d['senses']),
                freq=d['freq'],
                deconjugation_process=d['deconjugation_process'],
                priority=d['priority'],
            ))
        return results

    def _calculate_priority(
            self,
            freq: int,
            form: Form,
            match_len: int,
            entry_senses: list,
    ) -> float:
        priority = float(match_len)

        # Frequency: log scale maps rank 1..999_999 evenly to ~0..10
        # rank 1 → ~10, rank 1000 → ~5, rank 50000 → ~2.8, rank 999_999 → 0
        # (KRDICT imports carry no ranks, so every entry scores 0 here and
        # the KRDICT ⭐ level stars in the tags carry that signal instead.)
        if freq < DEFAULT_FREQ:
            priority += 10.0 * (1.0 - math.log(freq) / math.log(DEFAULT_FREQ))

        # KRDICT level stars: +1 per star of the best sense. Only breaks
        # ties at equal match_len; longer matches still win overall.
        if entry_senses:
            priority += max(star_count(s.get('tags', [])) for s in entry_senses)

        # Deconjugation cost
        priority -= len(form.process)

        return priority
