from typing import Protocol


class TTSClient(Protocol):
    async def synthesize(self, text: str, seed: int = 0) -> bytes: ...
