"""Modal TTS API client supporting custom-voice and voice-design endpoints."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from aidente_voice.tts.api_logger import append_log

_RETRY_DELAYS = [1.0, 2.0, 4.0]
_DEFAULT_LOG_PATH = Path.home() / ".aidente" / "api_log.jsonl"


@dataclass
class CustomVoiceConfig:
    """Configuration for the /custom-voice endpoint.

    Speakers: Aiden, Dylan, Eric, Ono_anna, Ryan, Serena, Sohee, Uncle_fu, Vivian
    Languages: Auto, Chinese, English, Japanese, Korean, French, German,
               Spanish, Portuguese, Russian
    """

    speaker: str = "Ryan"
    language: str = "Auto"
    instruct: str | None = None


@dataclass
class VoiceDesignConfig:
    """Configuration for the /voice-design endpoint.

    instruct: natural language description of the desired voice.
    Example: "A warm, slightly raspy female voice speaking slowly"
    """

    instruct: str
    language: str = "Auto"


class ModalTTSClient:
    """TTS client for the Modal-hosted Qwen3-TTS API.

    Every API call (success or final failure) is appended to a JSONL log file.
    Set log_path=None to disable logging.
    """

    def __init__(
        self,
        endpoint_url: str,
        config: CustomVoiceConfig | VoiceDesignConfig | None = None,
        log_path: Path | None = _DEFAULT_LOG_PATH,
    ) -> None:
        self._url = endpoint_url
        self._config = config or CustomVoiceConfig()
        self._log_path = log_path

    def _build_payload(self, text: str, instruct: str | None = None) -> dict:
        if isinstance(self._config, VoiceDesignConfig):
            # self._config.instruct is the voice description (required field).
            # Merge per-sentence <style=...> as a suffix — never replace the voice description.
            voice_desc = self._config.instruct
            effective_instruct = f"{voice_desc}; {instruct}" if instruct else voice_desc
            return {
                "text": text,
                "language": self._config.language,
                "instruct": effective_instruct,
            }

        # CustomVoiceConfig: merge global instruct with per-call instruct from <style=...>.
        config_instruct = self._config.instruct
        if config_instruct and instruct:
            effective_instruct: str | None = f"{config_instruct}; {instruct}"
        else:
            effective_instruct = instruct or config_instruct

        payload: dict = {
            "text": text,
            "language": self._config.language,
            "speaker": self._config.speaker,
        }
        if effective_instruct:
            payload["instruct"] = effective_instruct
        return payload

    async def synthesize(self, text: str, seed: int = 0, instruct: str | None = None) -> bytes:
        """Synthesize text to audio bytes.

        Each call is logged to the JSONL log file (if log_path is set).
        seed is ignored — kept for interface compatibility.
        instruct overrides/merges with config-level instruct (from <style=...> tag).
        """
        payload = self._build_payload(text, instruct=instruct)
        last_exc: Exception | None = None
        last_status: int = 0

        t0 = time.monotonic()
        for delay in [0.0] + _RETRY_DELAYS:
            if delay:
                await asyncio.sleep(delay)
            try:
                response = requests.post(self._url, json=payload, timeout=60)
                last_status = response.status_code
                if response.status_code == 200:
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    self._log(payload, status=200, response_bytes=len(response.content), duration_ms=duration_ms)
                    return response.content
                last_exc = RuntimeError(
                    f"TTS API failed: status {response.status_code}: {response.text[:200]}"
                )
            except requests.RequestException as e:
                last_exc = e

        error_msg = f"TTS API failed after {len(_RETRY_DELAYS) + 1} attempts: {last_exc}"
        self._log(payload, status=last_status, error=error_msg)
        raise RuntimeError(error_msg)

    def _log(
        self,
        payload: dict,
        *,
        status: int,
        response_bytes: int | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        if self._log_path is None:
            return
        try:
            append_log(
                self._log_path,
                endpoint=self._url,
                request=payload,
                status=status,
                response_bytes=response_bytes,
                duration_ms=duration_ms,
                error=error,
            )
        except OSError:
            pass  # logging failure must never crash synthesis
