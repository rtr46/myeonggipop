# myeonggipop/ocr/providers/postprocessing.py
import logging
from typing import List

from myeonggipop.ocr.interface import Paragraph, Word, BoundingBox

logger = logging.getLogger(__name__)


def _merge_bounding_boxes(boxes: List[BoundingBox]) -> BoundingBox:
    """Creates a single BoundingBox that encompasses all provided boxes."""
    if not boxes:
        return BoundingBox(0, 0, 0, 0)

    min_x = min(b.center_x - b.width / 2 for b in boxes)
    max_x = max(b.center_x + b.width / 2 for b in boxes)
    min_y = min(b.center_y - b.height / 2 for b in boxes)
    max_y = max(b.center_y + b.height / 2 for b in boxes)

    width = max_x - min_x
    height = max_y - min_y
    center_x = min_x + width / 2
    center_y = min_y + height / 2

    return BoundingBox(center_x, center_y, width, height)


def _are_lines_adjacent(line1: Paragraph, line2: Paragraph) -> bool:
    """
    Determines if two lines are close enough to be considered part of the
    same paragraph. Lines should have significant x-overlap and be close
    on the y-axis. Heuristics tolerate small OCR inaccuracies.
    """
    b1, b2 = line1.box, line2.box
    x_overlap = max(0, min(b1.center_x + b1.width / 2, b2.center_x + b2.width / 2)
                    - max(b1.center_x - b1.width / 2, b2.center_x - b2.width / 2))
    has_enough_overlap = x_overlap > (min(b1.width, b2.width) * 0.5)

    # Allow up to 1.9x the height for line spacing.
    vertical_distance_ok = abs(b1.center_y - b2.center_y) < 1.9 * max(b1.height, b2.height)
    return has_enough_overlap and vertical_distance_ok


def _merge_lines_into_paragraph(lines: List[Paragraph]) -> Paragraph:
    """Merges a list of single-line Paragraphs into one cohesive Paragraph."""
    if not lines:
        return None

    # Horizontal text is read top-to-bottom
    lines.sort(key=lambda p: p.box.center_y)

    all_words: List[Word] = []
    full_text_parts: List[str] = []
    all_boxes: List[BoundingBox] = []

    for line in lines:
        all_words.extend(line.words)
        full_text_parts.append(line.full_text)
        all_boxes.append(line.box)

    full_text = "".join(full_text_parts)
    merged_box = _merge_bounding_boxes(all_boxes)

    return Paragraph(
        full_text=full_text,
        words=all_words,
        box=merged_box,
    )


def group_lines_into_paragraphs(lines: List[Paragraph]) -> List[Paragraph]:
    """
    Takes a flat list of single-line Paragraphs and groups them into
    multi-line Paragraphs based on proximity.
    """
    if not lines:
        return []

    processed_paragraphs = []
    line_set = list(lines)
    while line_set:
        current_group = [line_set.pop(0)]
        i = 0
        while i < len(line_set):
            line_to_check = line_set[i]
            is_adjacent_to_group = any(
                _are_lines_adjacent(grouped_line, line_to_check) for grouped_line in current_group)

            if is_adjacent_to_group:
                current_group.append(line_set.pop(i))
                # Restart check from the beginning since the group has grown
                i = 0
            else:
                i += 1

        merged_para = _merge_lines_into_paragraph(current_group)
        if merged_para:
            processed_paragraphs.append(merged_para)

    logger.debug(f"Regrouped {len(lines)} raw OCR lines into {len(processed_paragraphs)} paragraphs.")
    return processed_paragraphs
