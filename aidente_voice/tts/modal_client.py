"""Modal TTS API client supporting custom-voice and voice-design endpoints."""

import asyncio
from dataclasses import dataclass

import requests

_RETRY_DELAYS = [1.0, 2.0, 4.0]


@dataclass
class CustomVoiceConfig:
    """Configuration for the /custom-voice endpoint.

    Uses a predefined speaker with optional style instruction.

    Speakers: Aiden, Dylan, Eric, Ono_anna, Ryan, Serena, Sohee, Uncle_fu, Vivian
    Languages: Auto, Chinese, English, Japanese, Korean, French, German,
               Spanish, Portuguese, Russian
    """

    speaker: str = "Ryan"
    language: str = "Japanese"
    instruct: str | None = None


@dataclass
class VoiceDesignConfig:
    """Configuration for the /voice-design endpoint.

    Creates a voice from a natural language description.

    Example instruct: "A warm, slightly raspy female voice speaking slowly"
    """

    instruct: str
    language: str = "Auto"


class ModalTTSClient:
    """TTS client for the Modal-hosted Qwen3-TTS API.

    Supports /custom-voice (predefined speaker) and /voice-design (description-based).
    The seed parameter is accepted for interface compatibility but ignored — the API
    uses LLM temperature sampling to produce natural variation across calls.
    """

    def __init__(
        self,
        endpoint_url: str,
        config: CustomVoiceConfig | VoiceDesignConfig | None = None,
    ) -> None:
        self._url = endpoint_url
        self._config = config or CustomVoiceConfig()

    def _build_payload(self, text: str) -> dict:
        if isinstance(self._config, VoiceDesignConfig):
            return {
                "text": text,
                "language": self._config.language,
                "instruct": self._config.instruct,
            }
        # CustomVoiceConfig
        payload: dict = {
            "text": text,
            "language": self._config.language,
            "speaker": self._config.speaker,
        }
        if self._config.instruct:
            payload["instruct"] = self._config.instruct
        return payload

    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        """Synthesize text to audio bytes.

        The seed parameter is ignored — repeated calls naturally produce
        different output due to LLM sampling (used by Gacha feature).
        """
        payload = self._build_payload(text)
        last_exc: Exception | None = None

        for delay in [0.0] + _RETRY_DELAYS:
            if delay:
                await asyncio.sleep(delay)
            try:
                response = requests.post(self._url, json=payload, timeout=60)
                if response.status_code == 200:
                    return response.content
                last_exc = RuntimeError(
                    f"TTS API failed: status {response.status_code}: {response.text[:200]}"
                )
            except requests.RequestException as e:
                last_exc = e

        raise RuntimeError(
            f"TTS API failed after {len(_RETRY_DELAYS) + 1} attempts: {last_exc}"
        )
