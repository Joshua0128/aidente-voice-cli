import asyncio
import requests
from aidente_voice.tts.client import TTSClient  # noqa: F401 (for type checking)

_RETRY_DELAYS = [1.0, 2.0, 4.0]


class ModalTTSClient:
    def __init__(self, endpoint_url: str) -> None:
        self._url = endpoint_url

    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        payload = {"text": text, "seed": seed}
        last_exc: Exception | None = None

        for attempt, delay in enumerate([0.0] + _RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = requests.post(self._url, json=payload, timeout=60)
                if response.status_code == 200:
                    return response.content
                last_exc = RuntimeError(
                    f"TTS API failed: status {response.status_code}"
                )
            except requests.RequestException as e:
                last_exc = e

        raise RuntimeError(
            f"TTS API failed after {len(_RETRY_DELAYS) + 1} attempts: {last_exc}"
        )
