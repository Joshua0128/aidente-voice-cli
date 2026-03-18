# aidente-voice-cli Design Spec
**Date:** 2026-03-18
**Status:** Approved

---

## 1. Problem Statement

生成式 TTS 的三個核心痛點：

1. **語速不可控** — 無法針對特定句子做慢速輸出
2. **留白不精準** — 句間靜音長度無法指定
3. **自然笑聲缺失** — 無法插入真人錄音質感的輕笑聲

---

## 2. Solution Overview

`aidente-voice-cli` 是一個命令列工具，作為 Qwen3-TTS（透過 Modal API 部署）與最終音訊產出之間的「工程控制層」。使用者在純文字腳本中嵌入控制標籤，CLI 負責解析、並發生成、後處理、互動抽卡、精確拼接。

---

## 3. Custom Tag System

| 標籤 | 說明 | 處理層 |
|---|---|---|
| `<pause=X>` | 插入 X 秒絕對靜音 | assembler |
| `<speed=X>` | 對前一句套用無損變速（不改變音高） | postprocess |
| `<gacha=N>` | 生成 N 個 seed 版本，終端機人工選擇 | orchestrator |
| `<sfx=laugh>` | 從 clip 庫 splice 笑聲音檔 | assembler |
| `<sfx=laugh,fade=X>` | 同上，自訂 fade-in/out 秒數（預設 0.05s） | assembler |

---

## 4. Architecture

### 4.1 Module Structure

```
aidente_voice/
├── cli.py              # Typer CLI 入口
├── parser.py           # 標籤解析 + 語義切塊
├── tts/
│   ├── client.py       # TTSClient Protocol (adapter interface)
│   └── modal_client.py # Modal API 實作
├── pipeline/
│   ├── orchestrator.py # AsyncIO 主管線協調器
│   ├── postprocess.py  # atempo time-stretch
│   └── assembler.py    # 拼接 + silence + sfx splice
├── gacha.py            # 終端機互動抽卡邏輯
└── audio_player.py     # macOS afplay 播放封裝
```

### 4.2 Data Flow

```
script.txt
    ↓ parser.py
[Chunk[]]           ← text + tags metadata
    ↓ orchestrator.py (asyncio.gather + Semaphore)
[AudioChunk[]]      ← bytes in-memory (or ./chunks/ if --keep-chunks)
    ↓ postprocess.py
[ProcessedChunk[]]  ← speed-adjusted / silence segments
    ↓ gacha.py      ← interactive selection (if gacha chunks exist)
    ↓ assembler.py
final_output.wav
```

### 4.3 TTSClient Adapter Interface

```python
class TTSClient(Protocol):
    async def synthesize(self, text: str, seed: int = 0) -> bytes: ...
```

`ModalTTSClient` 實作此 Protocol，處理 HTTP 請求、回傳 bytes、retry 邏輯。未來替換 TTS 後端只需換實作，pipeline 不動。

---

## 5. Chunk Data Structure

```python
@dataclass
class Chunk:
    index: int
    type: Literal["tts", "pause", "sfx", "gacha"]
    text: str | None = None        # tts / gacha
    duration: float | None = None  # pause
    speed: float = 1.0             # tts / gacha speed modifier
    gacha_n: int = 1               # gacha 版本數
    sfx_name: str | None = None    # sfx clip 名稱 (e.g., "laugh")
    sfx_fade: float = 0.05         # sfx fade-in/out 秒數
```

**斷句規則：** 依 `。！？\n` 切割。`<speed=X>` 標籤附著在前一個句子的 chunk 上，不單獨成為 chunk。

**解析範例：**
```
接下來我們要講述一個非常關鍵的底層概念。 <speed=0.85>
很多人在這裡會搞錯， <pause=0.5> <gacha=3> <sfx=laugh> 其實這沒有想像中困難。
```

輸出：
```
[0] tts   "接下來我們要講述一個非常關鍵的底層概念。"  speed=0.85
[1] tts   "很多人在這裡會搞錯，"
[2] pause  duration=0.5
[3] gacha  "其實這沒有想像中困難。"  n=3
[4] sfx   sfx_name="laugh"  sfx_fade=0.05
```

---

## 6. AsyncIO Orchestrator

### Phase 1 vs Phase 3 Async Strategy

- **Phase 1：** `orchestrator.py` 使用 `asyncio.run()` 包裝，內部用 **sequential `await`**（一個 chunk 完成再送下一個）。TTSClient 介面已是 `async def`，Phase 3 升級時 `orchestrator.py` 只需改成 `asyncio.gather()`，其他模組不動。
- **Phase 3：** 改用 `asyncio.gather()` 並發所有請求，加入 `asyncio.Semaphore(max_concurrent)` 防止 Modal rate-limit flooding。

**Gacha 時序：** 全部 TTS 完成後，依序呈現所有 gacha 互動，不在生成途中打斷。

`--keep-chunks` 時輸出到 `./chunks/`，gacha 的 N 個版本全部保留。目錄若已存在則**覆蓋**（舊檔案直接被同名新檔取代），不中止執行。

### Gacha Seed Strategy

N 個版本的 seed 使用**固定遞增序列**：`[42, 1337, 7, 999, ...]`（預定義列表，取前 N 個）。這確保跨 run 的可重現性——相同腳本多次執行，同一個 gacha chunk 永遠生成相同的 N 個候選，方便 debug。Seed 列表硬編碼在 `gacha.py` 中，不對外暴露設定。

### Audio Spec Pin

Qwen3-TTS 輸出規格：**24kHz, mono, 16-bit PCM**。所有 silence 生成與 sfx clip 必須使用相同規格，pydub 不自動 resample。

---

## 7. Post-Processing: Speed Control

使用 FFmpeg `atempo` 濾鏡（WSOLA 演算法），不改變音高與音色。

**Auto-chain 規則：** `atempo` 單一 instance 範圍限制 0.5–2.0。超出範圍自動鏈接：

```
speed=0.3  →  atempo=0.5,atempo=0.6   (0.5 × 0.6 = 0.3)
speed=0.85 →  atempo=0.85             (單一 instance)
```

實作層自動計算鏈接，使用者無需關心此細節。建議最低 speed 為 0.6x，低於此值 WSOLA 可能產生可聞的音質劣化。

---

## 8. SFX Splice

- clip 庫預設路徑：`~/.aidente/sfx/`，檔名對應 sfx 名稱（`laugh.wav`）
- 使用者可自行錄製並替換 clip
- 每個 sfx clip 在 splice 前自動套用 fade-in/out（預設 50ms）
- `<sfx=laugh,fade=0>` 可停用 fade（硬接）

**SFX Sample Rate 處理：** 若 sfx clip 的 sample rate / channel 與音訊規格（24kHz mono）不符，`assembler.py` 自動用 pydub `.set_frame_rate(24000).set_channels(1)` 轉換，並印出警告：
```
[WARN] sfx/laugh.wav is 44100Hz stereo — auto-converting to 24kHz mono.
```
轉換後才 splice，原始 clip 檔案不被修改。

---

## 9. Gacha Interactive UX

```
━━━━━━━━━━━━━━━━━  GACHA 1/2  ━━━━━━━━━━━━━━━━━
 "其實這沒有想像中困難。"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 [1] ▶  Playing... (seed 42)
 [2]    Option 2
 [3]    Option 3

 Controls: [1/2/3] play option  [Enter] confirm selection  [q] quit
>
```

- 單鍵輸入（無需 Enter 播放）：`termios` + `tty` raw mode
- 音訊播放：`subprocess.run(["afplay", path])`（macOS 內建，blocking，播完才回到互動介面）
- 多個 gacha 標籤：依序處理，顯示進度（GACHA 1/2、2/2）

**邊界情況：**

- **未先播放直接按 Enter：** 自動播放 Option 1，播完後顯示 `▶ Played Option 1. Press [Enter] again to confirm, or [1/2/3] to play another.`
- **按 `q` 中止：** 印出 `[WARN] Gacha aborted. Assembling with selections so far. Unselected gacha chunks will use Option 1 as default.` 並繼續執行，未選的 gacha chunk 以 Option 1（seed 42）填入。
- **`<speed=X>` 出現在腳本第一行（無前置 chunk）：** parser 拋出 `ParseError: <speed> tag at line 1 has no preceding sentence to attach to.` 並終止，不進行任何 API 呼叫。

---

## 10. CLI Interface

```
$ aidente-voice generate -i script.txt -o output.wav [flags]
```

| Flag | 預設值 | 說明 |
|---|---|---|
| `-i / --input` | 必填 | 輸入腳本路徑 |
| `-o / --output` | `output.wav` | 輸出音檔路徑 |
| `--sfx-dir` | `~/.aidente/sfx/` | SFX clip 庫目錄 |
| `--max-concurrent` | `10` | Modal API 最大並發數 |
| `--keep-chunks` | `false` | 保留中間音檔到 `./chunks/` |
| `--dry-run` | `false` | 只解析標籤，不生成，印出 chunk 清單 |

**`--dry-run` 範例：**
```
[DRY RUN] Parsed 5 chunks:
  [0] tts    "接下來我們要講述..." speed=0.85
  [1] tts    "很多人在這裡會搞錯，"
  [2] pause  0.5s
  [3] gacha  "其實這沒有想像中困難。" n=3
  [4] sfx    laugh fade=0.05
No API calls made.
```

---

## 11. Tech Stack

| 層次 | 技術選型 |
|---|---|
| CLI 框架 | Python + Typer |
| 文本解析 | Python `re` 模組 |
| TTS 後端 | Modal API（已部署 Qwen3-TTS） |
| 音訊處理 | pydub + ffmpeg-python |
| 並發 | asyncio + asyncio.Semaphore |
| 音訊播放 | macOS `afplay`（subprocess） |
| 終端機互動 | Python `termios` + `tty` |

---

## 11b. audio_player.py Interface

`audio_player.py` 封裝 macOS `afplay`，提供一個同步阻塞函數：

```python
def play(path: str | Path) -> None:
    """Play audio file via afplay. Blocks until playback completes."""
    subprocess.run(["afplay", str(path)], check=True)
```

- 播放期間 blocking（使用者按鍵不會中斷播放）
- `check=True` 確保 afplay 非零退出時拋出例外
- 未來擴充可換成 `playsound` 或 `pygame` 做跨平台支援，介面不變

---

## 11c. Error Handling Contract

| 錯誤情境 | 行為 |
|---|---|
| Modal API 呼叫失敗 | 自動 retry 3 次（指數退避：1s, 2s, 4s），仍失敗則 `[ERROR]` 印出並終止整個 pipeline |
| SFX 檔案不存在 | `[ERROR] SFX file not found: ~/.aidente/sfx/laugh.wav. Add the file or remove the <sfx> tag.` 並終止 |
| `<speed>` 在腳本第一行 | `[ERROR] ParseError: <speed> tag has no preceding sentence.` 並終止（不呼叫任何 API） |
| `ffmpeg` 未安裝 | `[ERROR] ffmpeg not found. Install via: brew install ffmpeg` 並終止 |
| SFX sample rate 不符 | `[WARN]` 自動轉換（見 Section 8），不中止 |
| `--keep-chunks` 目錄已存在 | 直接覆蓋，不中止，不提示 |

輸出音檔格式：**永遠寫成 WAV**，無論 `-o` 的副檔名為何。

---

## 12. Phase Rollout

| Phase | 功能 | 解決痛點 |
|---|---|---|
| **1 MVP** | CLI + parser + `<pause>` + `<speed>` + `<sfx>` + 基本拼接（sequential） | 全部 3 個痛點 |
| **2 Gacha** | `<gacha>` + 終端機互動抽卡 | 語氣多樣性控制 |
| **3 Async** | asyncio.gather 並發 + Semaphore + 進度條 | 長篇講義生成速度 |

Phase 1 交付後即可生產使用。Phase 2、3 為增量疊加，不需重構核心架構。
