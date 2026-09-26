# myeonggipop/gui/popup.py
import logging
import threading
from typing import List, Optional

from PyQt6.QtCore import QTimer, QPoint, QSize
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QFontInfo
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QApplication

from myeonggipop.config.config import config, IS_MACOS
from myeonggipop.dictionary.lookup import DictionaryEntry
from myeonggipop.gui.magpie_manager import magpie_manager

# macOS-specific imports for focus management
if IS_MACOS:
    try:
        import Quartz
    except ImportError:
        Quartz = None

logger = logging.getLogger(__name__)

# Sense tags whose words mark grammar entries (endings, particles,
# affixes); only these show verbose explanations. Matched per word so
# multi-word tags like 'Ending of a Word' work.
GRAMMAR_TAG_WORDS = {'Ending', 'Affix', 'Particle', 'Suffix', 'Prefix',
                     'Auxiliary'}


def _is_grammar_sense(sense) -> bool:
    for tag in sense.get('tags', []):
        for word in str(tag).split():
            if word in GRAMMAR_TAG_WORDS:
                return True
    return False


def star_count(tags) -> int:
    """Number of KRDICT level stars (⭐) across tag strings."""
    return sum(str(t).count('⭐') for t in (tags or []))


def split_stars(tags) -> tuple:
    """
    Split sense tags into (clean_tags, stars): 'Noun ⭐⭐⭐' becomes
    (['Noun'], 3). Tags without stars pass through unchanged.
    """
    clean, stars = [], 0
    for tag in (tags or []):
        stars += str(tag).count('⭐')
        stripped = str(tag).replace('⭐', '').strip()
        if stripped:
            clean.append(stripped)
    return clean, stars


def compact_gloss(written_form: str, text: str) -> str:
    """
    Shorten a sense gloss for popup display:
    - strip a leading headword echo (the header already shows it),
      including homograph numbers and separators left behind
      (e.g. "고양이|cat ..." -> "cat ...", "고1→ 물고" -> "→ 물고")
    - truncate to config.max_gloss_chars (0 = unlimited)
    """
    text = (text or '').strip()
    if written_form and text.startswith(written_form):
        text = text[len(written_form):].lstrip('0123456789 |:;')
    max_chars = config.max_gloss_chars
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip() + '…'
    return text


class Popup(QWidget):
    def __init__(self, shared_state, input_loop):
        super().__init__()
        self._latest_data = None
        self._last_latest_data = None
        self._data_lock = threading.Lock()
        self._previous_active_window_on_mac = None

        self.shared_state = shared_state
        self.input_loop = input_loop

        self.is_visible = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process_latest_data_loop)
        self.timer.start(10)

        self.probe_label = QLabel()
        self.probe_label.setWordWrap(True)
        self.probe_label.setTextFormat(Qt.TextFormat.RichText)

        self.is_calibrated = False
        self.header_chars_per_line = 50
        self.def_chars_per_line = 50

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self._apply_frame_stylesheet()
        main_layout.addWidget(self.frame)

        self.content_layout = QVBoxLayout(self.frame)
        self.content_layout.setContentsMargins(10, 10, 10, 10)

        self.display_label = QLabel()
        self.display_label.setWordWrap(True)
        self.display_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_layout.addWidget(self.display_label)

        self.hide()

    def _apply_frame_stylesheet(self):
        bg_color = QColor(config.color_background)
        r, g, b = bg_color.red(), bg_color.green(), bg_color.blue()
        a = config.background_opacity
        self.probe_label.setFont(QFont(config.font_family))
        self.frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({r}, {g}, {b}, {a});
                color: {config.color_foreground};
                border-radius: 8px;
                border: 1px solid #555;
            }}
            QLabel {{
                background-color: transparent;
                border: none;
                font-family: "{config.font_family}";
            }}
            hr {{
                border: none;
                height: 1px;
            }}
        """)

    def _calibrate_empirically(self):
        logger.debug("--- Calibrating Font Metrics Empirically (One-Time) ---")

        # Log font info
        actual_font = self.display_label.font()
        font_info = QFontInfo(actual_font)
        logger.debug(f"[FONT DEBUG] Requested font family: '{config.font_family}' (or default)")
        logger.debug(f"[FONT DEBUG]   -> Actual resolved font family: '{font_info.family()}'")
        logger.debug(f"[FONT DEBUG]   -> Actual style name: '{font_info.styleName()}'")
        logger.debug(f"[FONT DEBUG]   -> Actual point size: {font_info.pointSize()}")
        logger.debug(f"[FONT DEBUG]   -> Actual pixel size: {font_info.pixelSize()}")
        logger.debug(f"[FONT DEBUG]   -> Is it bold? {font_info.bold()}")

        margins = self.content_layout.contentsMargins()
        border_width = 1
        horizontal_padding = margins.left() + margins.right() + (border_width * 2)

        screen = QApplication.primaryScreen()
        self.max_content_width = (int(screen.geometry().width() * 0.4)) - horizontal_padding

        header_font = QFont(config.font_family)
        header_font.setPixelSize(config.font_size_header)
        header_metrics = QFontMetrics(header_font)
        self.header_chars_per_line = self._find_chars_for_width(header_metrics, "Header")

        def_font = QFont(config.font_family)
        def_font.setPixelSize(config.font_size_definitions)
        def_metrics = QFontMetrics(def_font)
        self.def_chars_per_line = self._find_chars_for_width(def_metrics, "Definition")

        logger.debug(f"[CALIBRATE] Max content width: {self.max_content_width}px")
        logger.debug(f"[CALIBRATE] Empirically found {self.header_chars_per_line} header chars/line")
        logger.debug(f"[CALIBRATE] Empirically found {self.def_chars_per_line} definition chars/line")
        self.is_calibrated = True

    def _find_chars_for_width(self, metrics: QFontMetrics, name: str) -> int:
        low = 1
        high = 500
        best_fit = 1

        while low <= high:
            mid = (low + high) // 2
            if mid == 0: break

            test_string = 'x' * mid
            current_width = metrics.horizontalAdvance(test_string)

            if current_width <= self.max_content_width:
                best_fit = mid
                low = mid + 1
            else:
                high = mid - 1

        return best_fit if best_fit > 0 else 50

    def set_latest_data(self, data):
        with self._data_lock:
            self._latest_data = data

    def get_latest_data(self):
        with self._data_lock:
            return self._latest_data

    def process_latest_data_loop(self):
        if not self.is_calibrated:
            self._calibrate_empirically()

        latest_data = self.get_latest_data()
        if latest_data and latest_data != self._last_latest_data:
            # update popup content
            full_html, new_size = self._calculate_content_and_size_char_count(latest_data)
            self.display_label.setText(full_html)
            self.setFixedSize(new_size)
        self._last_latest_data = latest_data

        if self._latest_data and self.input_loop.is_virtual_hotkey_down() and config.is_enabled:
            self.show_popup()
        else:
            self.hide_popup()

        mouse_pos = QCursor.pos()
        self.move_to(mouse_pos.x(), mouse_pos.y())

    def _calculate_content_and_size_char_count(self, entries: Optional[List[DictionaryEntry]]) -> tuple[
        Optional[str], Optional[QSize]]:
        if not self.is_calibrated: return None, None
        if not entries: return None, None

        all_html_parts = []
        max_ratio = 0.0

        for i, entry in enumerate(entries):
            if i > 0:
                all_html_parts.append('<hr style="margin-top: 0px; margin-bottom: 0px;">')

            header_text_calc = entry.written_form
            if entry.reading: header_text_calc += f" [{entry.reading}]"
            header_ratio = len(header_text_calc) / self.header_chars_per_line
            max_ratio = max(max_ratio, header_ratio)

            # --- HTML construction ---
            header_html = f'<span style="color: {config.color_highlight_word}; font-size:{config.font_size_header}px;">{entry.written_form}</span>'
            if entry.reading: header_html += f' <span style="color: {config.color_highlight_reading}; font-size:{config.font_size_header - 2}px;">[{entry.reading}]</span>'
            if entry.deconjugation_process and config.show_deconjugation:
                deconj_str = " ← ".join(p for p in entry.deconjugation_process if p)
                if deconj_str:
                    header_html += f' <span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.8;">({deconj_str})</span>'
            def_text_parts_calc = []
            def_text_parts_html = []
            senses = entry.senses
            hidden_senses = 0
            max_senses = config.max_senses_per_entry
            if max_senses and len(senses) > max_senses:
                hidden_senses = len(senses) - max_senses
                senses = senses[:max_senses]
            # Number senses only when several are shown; a lone "(1)" is noise.
            numbered = config.show_all_glosses and len(entry.senses) > 1
            for idx, sense in enumerate(senses):
                glosses = sense.get('glosses', [])
                verboses = sense.get('verbose', [])
                if config.show_all_glosses:
                    shown = list(enumerate(glosses))
                else:
                    shown = [(0, glosses[0])] if glosses else []
                glosses_str = ", ".join(
                    compact_gloss(entry.written_form, g) for _, g in shown)
                tags_list = sense.get('tags', [])
                clean_tags, stars = split_stars(tags_list)
                sense_calc = f"({idx + 1})" if numbered else ""
                sense_html = f"<b>({idx + 1})</b> " if numbered else ""
                if config.show_tags and clean_tags:
                    tags_str = f' [{", ".join(clean_tags)}]'
                    sense_calc += tags_str
                    sense_html += f'<span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.7;">{tags_str}</span> '
                if config.show_stars and stars:
                    stars_str = ' ' + '⭐' * stars
                    sense_calc += stars_str
                    sense_html += f'<span style="font-size:{config.font_size_definitions - 2}px;">{stars_str}</span> '
                hanja = sense.get('hanja', [])
                if config.show_hanja and hanja:
                    hanja_str = ' '.join(f'〔{h}〕' for h in hanja)
                    sense_calc += f' {hanja_str}'
                    sense_html += f'<span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.7;">{hanja_str}</span> '
                sense_calc += glosses_str
                sense_html += glosses_str
                # Verbose term explanations, only for grammar entries
                # (endings, particles, affixes) and only when enabled.
                if config.show_grammar_explanations and _is_grammar_sense(sense):
                    for gi, _g in shown:
                        if gi < len(verboses) and verboses[gi]:
                            v = compact_gloss('', verboses[gi])
                            if not v:
                                continue
                            sense_html += (
                                f'<br><span style="color:{config.color_foreground}; '
                                f'font-size:{config.font_size_definitions - 2}px; '
                                f'opacity:0.7;">{v}</span>')
                            sense_calc += f' {v}'
                def_text_parts_calc.append(sense_calc)
                def_text_parts_html.append(sense_html)

            if hidden_senses:
                more_calc = f"+{hidden_senses} more"
                more_html = (f'<span style="color:{config.color_foreground}; '
                             f'opacity:0.6;"><i>+{hidden_senses} more</i></span>')
                def_text_parts_calc.append(more_calc)
                def_text_parts_html.append(more_html)

            if config.compact_mode:
                separator = "; "
                full_def_text_html = separator.join(def_text_parts_html)
                def_ratio = len(separator.join(def_text_parts_calc)) / self.def_chars_per_line
                max_ratio = max(max_ratio, def_ratio)
            else:
                separator = "<br>"
                full_def_text_html = separator.join(def_text_parts_html)
                for def_text_calc in def_text_parts_calc:
                    def_ratio = len(def_text_calc) / self.def_chars_per_line
                    max_ratio = max(max_ratio, def_ratio)

            definitions_html_final = f'{" " if config.compact_mode else "<br>"}<span style="font-size:{config.font_size_definitions}px;">{full_def_text_html}</span>'
            all_html_parts.append(f"{header_html}{definitions_html_final}")

        optimal_content_width = self.max_content_width * min(1.0, max_ratio)
        optimal_content_width = max(optimal_content_width, 200)

        full_html = "".join(all_html_parts)
        self.probe_label.setText(full_html)

        final_height = self.probe_label.heightForWidth(int(optimal_content_width))

        margins = self.content_layout.contentsMargins()
        border_width = 1
        horizontal_padding = margins.left() + margins.right() + (border_width * 2)
        vertical_padding = margins.top() + margins.bottom() + (border_width * 2)

        final_size = QSize(int(optimal_content_width) + horizontal_padding, final_height + vertical_padding)
        return full_html, final_size

    def move_to(self, x, y):
        cursor_point = QPoint(x, y)
        screen = QApplication.screenAt(cursor_point) or QApplication.primaryScreen()
        screen_geo = screen.geometry()
        popup_size = self.size()
        offset = 15

        ratio = screen.devicePixelRatio()
        x, y = magpie_manager.transform_raw_to_visual((int(x), int(y)), ratio)

        # --- Positioning logic based on mode ---
        mode = config.popup_position_mode

        if mode == 'visual_novel_mode':
            # --- Vertical Position (VN Mode) ---
            screen_height = screen_geo.height()
            cursor_y_in_screen = y - screen_geo.top()
            is_below = True
            if cursor_y_in_screen > (2 * screen_height / 3):  # Lower third
                is_below = False  # Place above
            elif cursor_y_in_screen < (screen_height / 3):  # Upper third
                is_below = True  # Place below
            else:  # Middle third
                is_below = cursor_y_in_screen < (screen_height / 2)
            final_y = (y + offset) if is_below else (y - popup_size.height() - offset)

            # Vertical Push
            if final_y < screen_geo.top(): final_y = screen_geo.top()
            if final_y + popup_size.height() > screen_geo.bottom():
                final_y = screen_geo.bottom() - popup_size.height()

            # --- Horizontal Position (VN Mode) ---
            screen_width = screen_geo.width()
            cursor_x_in_screen = x - screen_geo.left()
            # Define anchor points for interpolation
            pos_right = x + offset
            pos_center = x - popup_size.width() / 2.0
            pos_left = x - popup_size.width() - offset

            # Interpolate smoothly between right, center, and left alignment
            if cursor_x_in_screen < screen_width / 2.0:
                ratio = cursor_x_in_screen / (screen_width / 2.0)
                final_x = pos_right * (1 - ratio) + pos_center * ratio
            else:
                ratio = (cursor_x_in_screen - (screen_width / 2.0)) / (screen_width / 2.0)
                final_x = pos_center * (1 - ratio) + pos_left * ratio

        elif mode == 'flip_horizontally':
            # X: Flip, Y: Push
            preferred_x = x + offset
            final_x = preferred_x if preferred_x + popup_size.width() <= screen_geo.right() else x - popup_size.width() - offset

            final_y = y + offset
            if final_y + popup_size.height() > screen_geo.bottom(): final_y = screen_geo.bottom() - popup_size.height()
            if final_y < screen_geo.top(): final_y = screen_geo.top()

        elif mode == 'flip_vertically':
            # X: Push, Y: Flip
            final_x = x + offset
            if final_x + popup_size.width() > screen_geo.right(): final_x = screen_geo.right() - popup_size.width()
            if final_x < screen_geo.left(): final_x = screen_geo.left()

            preferred_y = y + offset
            final_y = preferred_y if preferred_y + popup_size.height() <= screen_geo.bottom() else y - popup_size.height() - offset

        else:  # 'flip_both'
            # X: Flip
            preferred_x = x + offset
            final_x = preferred_x if preferred_x + popup_size.width() <= screen_geo.right() else x - popup_size.width() - offset

            # Y: Flip
            preferred_y = y + offset
            final_y = preferred_y if preferred_y + popup_size.height() <= screen_geo.bottom() else y - popup_size.height() - offset

        # Final clamp to ensure the popup is always fully visible.
        # This acts as a safeguard against any edge cases.
        final_x = max(screen_geo.left(), min(final_x, screen_geo.right() - popup_size.width()))
        final_y = max(screen_geo.top(), min(final_y, screen_geo.bottom() - popup_size.height()))

        self.move(int(final_x), int(final_y))

    def hide_popup(self):
        # logger.debug(f"hide_popup triggered while visibility:{self.is_visible}")
        if not self.is_visible:
            return
        self.hide()
        self.is_visible = False
        QTimer.singleShot(50, lambda: self._release_lock_safely())  # prevent popup from being screenshotted
        self._restore_focus_on_mac()

    def _release_lock_safely(self):
        logger.debug("hide_popup releasing lock...")
        self.shared_state.screen_lock.release()
        logger.debug("...successfully released lock by hide_popup")

    def show_popup(self):
        # logger.debug(f"show_popup triggered while visibility:{self.is_visible}")
        if self.is_visible:
            return
        logger.debug("show_popup acquiring lock...")
        self.shared_state.screen_lock.acquire()
        logger.debug("...successfully acquired lock by show_popup")

        self._store_active_window_on_mac()
        self.show()
        if IS_MACOS:
            self.raise_()

        self.is_visible = True

    def reapply_settings(self):
        logger.debug("Popup: Re-applying settings and triggering font recalibration.")
        self._apply_frame_stylesheet()
        # By setting is_calibrated to False, the main loop will automatically
        # run _calibrate_empirically() again with the new font settings.
        self.is_calibrated = False

    def _store_active_window_on_mac(self):
        """Store the currently active window for focus restoration (macOS only)."""
        if not IS_MACOS or not Quartz:
            return

        try:
            # Get the currently active application
            active_app = Quartz.NSWorkspace.sharedWorkspace().frontmostApplication()
            if active_app:
                # Store the application reference instead of trying to get the window
                # We'll use the application to restore focus later
                self._previous_active_window_on_mac = active_app
        except Exception as e:
            logger.warning(f"Failed to store active window: {e}")
            self._previous_active_window_on_mac = None

    def _restore_focus_on_mac(self):
        """Restore focus to the previously active application (macOS only)."""
        if not IS_MACOS or not Quartz or not self._previous_active_window_on_mac:
            return

        try:
            # Activate the previously active application
            self._previous_active_window_on_mac.activateWithOptions_(Quartz.NSApplicationActivateAllWindows)
        except Exception as e:
            logger.warning(f"Failed to restore focus: {e}")
        finally:
            # Clear the stored application reference
            self._previous_active_window_on_mac = None
