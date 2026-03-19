# aidente-voice 使用手冊

aidente-voice 是一個 TTS 製作工具，讓你在腳本裡用標籤精確控制語速、停頓、音效，以及互動式音色抽選（Gacha），最終輸出混音完成的音訊檔案。

---

## 目錄

1. [安裝](#安裝)
2. [設定 API](#設定-api)
3. [撰寫腳本](#撰寫腳本)
4. [標籤參考](#標籤參考)
5. [CLI 指令](#cli-指令)
6. [音效（SFX）](#音效sfx)
7. [Gacha 互動選音](#gacha-互動選音)
8. [常見用法範例](#常見用法範例)
9. [錯誤排除](#錯誤排除)

---

## 安裝

需求：Python 3.11+、[uv](https://docs.astral.sh/uv/)、ffmpeg

```bash
# 安裝 ffmpeg（macOS）
brew install ffmpeg

# 安裝 Python 依賴
uv sync
```

安裝完成後，`aidente-voice` 指令即可使用：

```bash
uv run aidente-voice --help
```

---

## 設定 API

本工具使用 Modal 部署的 Qwen3-TTS API，支援三種語音合成端點：

### 端點說明

| 端點 | 說明 | 必填參數 |
|------|------|---------|
| `/custom-voice` | 使用預設音色（**推薦**） | `speaker`, `language` |
| `/voice-design` | 用自然語言描述音色特質 | `instruct` |
| `/voice-clone` | 上傳參考音檔複製音色（CLI 暫不支援） | `ref_audio_b64` |

### 設定 MODAL_TTS_URL

`MODAL_TTS_URL` 必須指向你選擇的端點完整 URL：

```bash
# 使用預設音色（推薦，大多數場景）
export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"

# 或寫入 ~/.zshrc 永久生效
echo 'export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"' >> ~/.zshrc
source ~/.zshrc
```

---

## 撰寫腳本

腳本是一個純文字檔（`.txt`），直接撰寫要合成的台詞，並在需要的地方插入標籤。

**基本規則：**
- 日文句號 `。`、驚嘆號 `！`、問號 `？` 或換行會自動切分成獨立的語音片段
- 標籤放在句子**之後**，控制該句語速或插入停頓

**範例腳本 `script.txt`：**

```
こんにちは、今日もよろしくお願いします。
少しゆっくり話しましょうか。<speed=0.8>
<pause=1.5>
そうですね。
大丈夫ですよ！<speed=1.2>
```

---

## 標籤參考

### `<pause=秒數>`

插入靜音段落。

```
準備はよろしいですか。<pause=2>では、始めましょう。
```

| 參數 | 類型 | 說明 |
|------|------|------|
| 秒數 | 浮點數 | 靜音長度（秒），例如 `0.5`、`1`、`2.5` |

---

### `<speed=倍率>`

調整**前一句**的語速。放在句子後方。

```
早口で話します。<speed=1.4>
ゆっくり話します。<speed=0.7>
```

| 參數 | 類型 | 說明 |
|------|------|------|
| 倍率 | 浮點數 | `1.0` 為正常速度，`< 1.0` 變慢，`> 1.0` 加快。支援範圍：`0.1` ～ `5.0` |

> **注意：** `<speed>` 必須放在一個句子後面，不能獨立存在。

---

### `<sfx=音效名[,fade=秒數]>`

在當前位置插入音效。

```
<sfx=laugh>
<sfx=laugh,fade=0.3>
```

| 參數 | 類型 | 說明 |
|------|------|------|
| 音效名 | 字串 | 對應 `--sfx-dir` 目錄下的 `.wav` 檔案名稱（不含副檔名） |
| `fade` | 浮點數（選填）| 淡入淡出時間（秒），預設 `0.05` |

---

### `<gacha=N>`

對**前一句**合成 N 個音色變體，讓你互動選擇最滿意的版本。

```
この台詞は何度も録り直したい。<gacha=4>
```

| 參數 | 類型 | 說明 |
|------|------|------|
| N | 整數 | 要合成的變體數量（1 ～ 8） |

Qwen3-TTS 每次推理都有 LLM 採樣，所以即使相同文字也會產生不同語調/節奏的版本。

---

## CLI 指令

### `aidente-voice generate`

```bash
uv run aidente-voice generate -i <腳本路徑> [選項]
```

#### 基本選項

| 選項 | 縮寫 | 預設值 | 說明 |
|------|------|--------|------|
| `--input` | `-i` | **必填** | 輸入腳本路徑（`.txt`） |
| `--output` | `-o` | `output.wav` | 輸出音訊路徑 |
| `--sfx-dir` | — | `~/.aidente/sfx` | 音效檔案目錄 |
| `--max-concurrent` | — | `10` | 最大同時合成請求數 |
| `--keep-chunks` | — | `false` | 保留個別片段（存到 `./chunks/`） |
| `--dry-run` | — | `false` | 只顯示解析結果，不呼叫 API |

#### 音色選項（`/custom-voice` 端點）

| 選項 | 預設值 | 說明 |
|------|--------|------|
| `--speaker` | `Ryan` | 音色名稱，見下表 |
| `--language` | `Japanese` | 語言提示 |
| `--instruct` | 無 | 風格描述，例如 `"Speak slowly with a warm tone"` |

**可選音色（`--speaker`）：**

| 名稱 | 特性 |
|------|------|
| `Ryan`（預設） | 成熟男聲 |
| `Aiden` | 年輕男聲 |
| `Dylan` | 低沉男聲 |
| `Eric` | 中性男聲 |
| `Serena` | 成熟女聲 |
| `Vivian` | 活潑女聲 |
| `Sohee` | 韓系女聲 |
| `Ono_anna` | 日系女聲 |
| `Uncle_fu` | 老者男聲 |

**可選語言（`--language`）：**

`Auto`、`Chinese`、`English`、`Japanese`、`Korean`、`French`、`German`、`Spanish`、`Portuguese`、`Russian`

#### 音色設計選項（`/voice-design` 端點）

| 選項 | 說明 |
|------|------|
| `--voice-design <描述>` | 用自然語言描述音色，自動切換到 `/voice-design` 端點 |

使用 `--voice-design` 時，`--speaker` 會被忽略；`--language` 仍然有效。

---

## 音效（SFX）

音效檔案必須是 `.wav` 格式，放在 `--sfx-dir` 指定的目錄（預設 `~/.aidente/sfx/`）。工具會自動將音效重新取樣為 24kHz 單聲道。

```bash
# 建立音效目錄並放入音效檔
mkdir -p ~/.aidente/sfx
cp /path/to/laugh.wav ~/.aidente/sfx/
```

---

## Gacha 互動選音

當腳本包含 `<gacha=N>` 標籤時，工具會先合成所有普通語音（並發執行），再逐一進入 Gacha 選音介面。

### 操作方式

```
[Gacha] Chunk 2: 'この台詞は何度も録り直したい。'
  Variants: 4 | Keys: 1-4 to play, Enter to confirm, q to quit
```

| 按鍵 | 動作 |
|------|------|
| `1` ～ `N` | 試聽對應變體 |
| `Enter` | 確認選擇（若尚未試聽，自動播放第一個） |
| `q` | 放棄選擇，使用第一個變體 |

---

## 常見用法範例

### 快速測試（不呼叫 API）

```bash
uv run aidente-voice generate -i script.txt --dry-run
```

輸出範例：
```
[DRY RUN] Parsed 4 chunks:
  [0] tts    "こんにちは、今日もよろしくお願いします。"
  [1] tts    "少しゆっくり話しましょうか。" speed=0.8
  [2] pause  1.5s
  [3] tts    "そうですね。"
No API calls made.
```

### 基本合成（使用預設音色 Ryan）

```bash
export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"
uv run aidente-voice generate -i script.txt -o output.wav
```

### 換音色

```bash
uv run aidente-voice generate -i script.txt --speaker Ono_anna --language Japanese
```

### 加上風格描述

```bash
uv run aidente-voice generate -i script.txt \
  --speaker Serena \
  --instruct "Speak slowly and warmly, like talking to a friend"
```

### 用自然語言設計音色

```bash
uv run aidente-voice generate -i script.txt \
  --voice-design "A slightly husky male voice with a calm and reassuring tone"
```

### 保留個別片段（方便逐段檢查）

```bash
uv run aidente-voice generate -i script.txt --keep-chunks
# 個別片段存在 ./chunks/chunk_000_tts.wav 等
```

### 使用自訂音效目錄

```bash
uv run aidente-voice generate -i script.txt --sfx-dir ./project_sfx
```

### 限制並發請求（穩定優先）

```bash
uv run aidente-voice generate -i script.txt --max-concurrent 3
```

---

## 錯誤排除

### `MODAL_TTS_URL environment variable not set`

```bash
export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"
```

### `Input file not found`

```bash
uv run aidente-voice generate -i ./script.txt  # 確認路徑正確
```

### `ParseError: <speed> with no preceding sentence`

`<speed>` 必須緊跟在句子後：

```
# ❌ 錯誤
<speed=0.8>こんにちは。

# ✅ 正確
こんにちは。<speed=0.8>
```

### `SFX file not found`

確認音效檔名與標籤一致（不含副檔名）：

```bash
ls ~/.aidente/sfx/
# 應看到 laugh.wav 等
```

### API 回傳 422 Unprocessable Entity

確認 `MODAL_TTS_URL` 指向正確端點，且 `--speaker` 值在允許清單內：

```
Aiden, Dylan, Eric, Ono_anna, Ryan, Serena, Sohee, Uncle_fu, Vivian
```

### API 持續失敗

工具自動重試 4 次（延遲 1s → 2s → 4s）。若持續失敗，可至 Modal Dashboard 確認服務狀態，或以 `--max-concurrent 1` 降低並發壓力。
