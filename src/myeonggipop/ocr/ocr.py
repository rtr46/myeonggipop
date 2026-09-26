# myeonggipop/ocr/ocr.py
import importlib
import inspect
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Type, Optional

from myeonggipop.config.config import config
from myeonggipop.ocr.interface import OcrProvider
from myeonggipop.ocr.providers.glensv2 import GoogleLensOcrV2
from myeonggipop.ocr.providers.screenai import ScreenAiOcr

logger = logging.getLogger(__name__)  # Get the logger

# Preferred providers, in order. Screen AI is the Korean-fork default
# (local, reads Hangul); Google Lens is the fallback when Screen AI
# components are missing.
DEFAULT_PROVIDER_NAMES = [ScreenAiOcr.NAME, GoogleLensOcrV2.NAME]


class OcrProcessor(threading.Thread):
    def __init__(self, shared_state, screen_manager):
        super().__init__(daemon=True, name="OcrProcessor")
        self.shared_state = shared_state
        self.screen_manager = screen_manager
        self.ocr_backend: Optional[OcrProvider] = None

        self.available_providers = self._discover_providers()
        if not self.available_providers:
            logger.critical("No OCR providers found! The application cannot continue.")
            sys.exit(1)

        self._load_provider_from_config()

    def run(self):
        logger.debug("OCR thread started.")
        while self.shared_state.running:
            try:
                screenshot = self.shared_state.ocr_queue.get()
                if not self.shared_state.running: break

                logger.debug("OCR: Triggered!")

                start_time = time.perf_counter()
                ocr_result = self.ocr_backend.scan(screenshot)
                logger.info(
                    f"{self.ocr_backend.NAME} found {len(ocr_result) if ocr_result else 0} paragraphs in {(time.perf_counter() - start_time):.3f}s.")
                # todo keep last ocr result?

                self.shared_state.hit_scan_queue.put(ocr_result)
            except:
                logger.exception("An unexpected error occurred in the ocr loop. Continuing...")
            finally:
                if config.auto_scan_mode:
                    self.shared_state.screenshot_trigger_event.set()
        logger.debug("OCR thread stopped.")

    # todo combine methods?
    def switch_provider(self, provider_name: str):
        if self.ocr_backend and provider_name == self.ocr_backend.NAME:
            return

        if provider_name in self.available_providers:
            logger.info(f"Switching OCR provider to '{provider_name}'...")
            provider_class = self.available_providers[provider_name]
            try:
                self.ocr_backend = provider_class()
                logger.info(f"Successfully switched OCR provider to '{self.ocr_backend.NAME}'")
                config.ocr_provider = self.ocr_backend.NAME
                config.save()  # todo fix tray showing wrong provider
                if config.auto_scan_mode:
                    self.shared_state.hit_scan_queue.put(None)
                    self.screen_manager.force_screenshot_trigger()
                    self.shared_state.screenshot_trigger_event.set()
            except Exception as e:
                logger.error(f"Failed to instantiate provider '{provider_name}': {e}", exc_info=True)
                if self.ocr_backend:
                    logger.info(f"Reverting to previous provider '{self.ocr_backend.NAME}'.")
                    config.ocr_provider = self.ocr_backend.NAME
                    config.save()  # todo fix tray showing wrong provider

        else:
            logger.error(f"Attempted to switch to an unknown provider: '{provider_name}'")

    def _load_provider_from_config(self):
        configured_provider_name = config.ocr_provider

        # Candidate list: the configured provider first (if it is still
        # available; a stale name such as upstream meikipop's
        # 'meikiocr (local)' simply falls through), then the built-in
        # defaults in order.
        candidates = []
        if configured_provider_name in self.available_providers:
            candidates.append(configured_provider_name)
        else:
            logger.warning(
                f"Configured OCR provider '{configured_provider_name}' not found. "
                f"Falling back to defaults: {DEFAULT_PROVIDER_NAMES}."
            )
        for name in DEFAULT_PROVIDER_NAMES:
            if name in self.available_providers and name not in candidates:
                candidates.append(name)
        if not candidates and self.available_providers:
            candidates.append(list(self.available_providers.keys())[0])

        last_error = None
        for provider_to_load_name in candidates:
            provider_class = self.available_providers[provider_to_load_name]
            try:
                self.ocr_backend = provider_class()
                logger.info(f"Initialized OCR with '{provider_to_load_name}' provider.")
                config.ocr_provider = provider_to_load_name
                return
            except Exception as e:
                logger.warning(
                    f"Failed to instantiate provider '{provider_to_load_name}': {e}. "
                    f"Trying next fallback..."
                )
                last_error = e

        logger.critical(
            f"No OCR provider could be initialized: {last_error}", exc_info=True)
        sys.exit(1)

    def _discover_providers(self) -> Dict[str, Type[OcrProvider]]:
        providers: Dict[str, Type[OcrProvider]] = {}

        # Get the package base path
        import myeonggipop
        package_dir = Path(myeonggipop.__file__).parent
        providers_path = package_dir / "ocr" / "providers"

        logger.debug(f"Scanning for providers in: {providers_path}")
        for subdir in providers_path.iterdir():
            if subdir.is_dir() and (subdir / "__init__.py").exists():
                provider_name = subdir.name
                try:
                    module_name = f"myeonggipop.ocr.providers.{provider_name}"
                    provider_module = importlib.import_module(module_name)
                    logger.debug(f"Found potential provider package: '{provider_name}'")

                    for _, obj_class in inspect.getmembers(provider_module, inspect.isclass):
                        if issubclass(obj_class,
                                      OcrProvider) and obj_class is not OcrProvider and not inspect.isabstract(
                            obj_class):
                            providers[obj_class.NAME] = obj_class
                            logger.debug(f" -> Discovered provider: '{obj_class.NAME}'")

                except ImportError as e:
                    logger.warning(f"Could not import or inspect provider '{provider_name}': {e}")
        return providers
