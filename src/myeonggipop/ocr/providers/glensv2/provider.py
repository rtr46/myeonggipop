# glensv2/provider.py
import io
import logging
import math
import random
import re
import time
from typing import Optional, List, Tuple

import requests
from PIL import Image

from myeonggipop.config.config import config
from myeonggipop.ocr.interface import OcrProvider, Paragraph, Word, BoundingBox
from myeonggipop.ocr.providers.glensv2.lens_betterproto import LensOverlayServerRequest, \
    LensOverlayServerResponse
from myeonggipop.ocr.providers.postprocessing import group_lines_into_paragraphs

# CJK ideographs (Hanja appear in Korean text) plus kana ranges
CJK_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')
# Hangul syllables, Hangul jamo and compatibility jamo
KOREAN_REGEX = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]')

logger = logging.getLogger(__name__)


class GoogleLensOcrV2(OcrProvider):
    NAME = "Google Lens (remote)"

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/x-protobuf', 'X-Goog-Api-Key': 'AIzaSyDr2UxVnv_U85AbhhY8XSHSIavUW0DC-sY',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

    def _process_image_for_upload(self, image: Image.Image) -> Tuple[bytes, int, int]:
        if config.glens_low_bandwidth:
            scale_factor = math.sqrt(0.5)
            new_width = int(image.width * scale_factor)
            new_height = int(image.height * scale_factor)
            processed_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            processed_image = processed_image.convert('L').quantize(colors=16)
            with io.BytesIO() as bio:
                processed_image.save(bio, format='PNG')
                return bio.getvalue(), new_width, new_height
        else:
            processed_image = image if image.mode == 'RGB' else image.convert('RGB')
            with io.BytesIO() as bio:
                processed_image.save(bio, format='JPEG', quality=90)
                return bio.getvalue(), image.width, image.height

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        start_time = time.perf_counter()
        image_bytes, final_width, final_height = self._process_image_for_upload(image)
        request = LensOverlayServerRequest()
        request.objects_request.request_context.request_id.uuid = random.randint(0, 2 ** 64 - 1)
        request.objects_request.image_data.payload.image_bytes = image_bytes
        request.objects_request.image_data.image_metadata.width = final_width
        request.objects_request.image_data.image_metadata.height = final_height

        try:
            request_duration = time.perf_counter() - start_time
            logger.debug(f"Request created in {request_duration:.2f}s. Sending screenshot for OCR...")
            start_time_req = time.perf_counter()
            response = self._session.post(
                'https://lensfrontend-pa.googleapis.com/v1/crupload',
                data=request.SerializeToString(), timeout=10
            )
            network_duration = time.perf_counter() - start_time_req
            response.raise_for_status()
            logger.debug(f"OCR response received in {network_duration:.2f}s. Processing...")

            glens_response = LensOverlayServerResponse().FromString(response.content)

            raw_lines = []
            if glens_response.objects_response.text.text_layout:
                for para in glens_response.objects_response.text.text_layout.paragraphs:
                    for line in para.lines:
                        line_has_cjk = any(CJK_REGEX.search(w.plain_text) for w in line.words)
                        line_has_korean = any(KOREAN_REGEX.search(w.plain_text) for w in line.words)
                        if not line_has_cjk and not line_has_korean:
                            continue

                        words_in_line = []
                        full_line_text = ""
                        word_texts = []
                        for word in line.words:
                            # Lens word texts may carry surrounding spaces;
                            # normalize them: strip here, re-join below using
                            # the API-provided separator (usually ' ') so
                            # eojeol boundaries survive (Korean) instead of
                            # being silently merged.
                            t = word.plain_text.strip()
                            if not t:
                                continue
                            sep = getattr(word, 'text_separator', None) or ''
                            w_box = BoundingBox(
                                center_x=word.geometry.bounding_box.center_x,
                                center_y=word.geometry.bounding_box.center_y,
                                width=word.geometry.bounding_box.width,
                                height=word.geometry.bounding_box.height,
                            )
                            word_texts.append((t, sep, w_box))

                        for i, (t, sep, w_box) in enumerate(word_texts):
                            if i == len(word_texts) - 1:
                                sep = ''
                            elif not sep:
                                sep = ' '
                            words_in_line.append(Word(text=t, separator=sep, box=w_box))
                            full_line_text += t + sep

                        if full_line_text.strip():
                            l_box = BoundingBox(
                                center_x=line.geometry.bounding_box.center_x,
                                center_y=line.geometry.bounding_box.center_y,
                                width=line.geometry.bounding_box.width,
                                height=line.geometry.bounding_box.height,
                            )
                            # Create a temporary Paragraph object for each line
                            raw_lines.append(
                                Paragraph(full_text=full_line_text.strip(), words=words_in_line, box=l_box)
                            )

            return group_lines_into_paragraphs(raw_lines)

        except requests.RequestException as e:
            logger.error("OCR Request Failed: %s", e)
            return None
