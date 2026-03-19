"""Modal TTS API client supporting custom-voice and voice-design endpoints."""

import asyncio
from dataclasses import dataclass

import requests

_RETRY_DELAYS = [1.0, 2.0, 4.0]


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

    Supports /custom-voice and /voice-design endpoints.
    Per-call instruct (from <style=...> tags) overrides the config-level instruct.
    """

    def __init__(
        self,
        endpoint_url: str,
        config: CustomVoiceConfig | VoiceDesignConfig | None = None,
    ) -> None:
        self._url = endpoint_url
        self._config = config or CustomVoiceConfig()

    def _build_payload(self, text: str, instruct: str | None = None) -> dict:
        # Merge global config instruct with per-call instruct (from <style=...> tag).
        # Both present: "global; per-sentence" so the model sees full context.
        # Only one present: use whichever exists.
        config_instruct = self._config.instruct if isinstance(self._config, CustomVoiceConfig) else None
        if config_instruct and instruct:
            effective_instruct = f"{config_instruct}; {instruct}"
        else:
            effective_instruct = instruct or config_instruct

        if isinstance(self._config, VoiceDesignConfig):
            return {
                "text": text,
                "language": self._config.language,
                "instruct": effective_instruct or self._config.instruct,
            }

        # CustomVoiceConfig
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

        Args:
            text: Text to synthesize.
            seed: Ignored (API uses LLM sampling for variation; kept for interface compat).
            instruct: Per-call style override, e.g. from <style=...> tag.
                      Overrides config-level instruct for this call only.
        """
        payload = self._build_payload(text, instruct=instruct)
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
