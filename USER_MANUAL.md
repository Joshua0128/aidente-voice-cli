# aidente-voice 使用手冊

aidente-voice 是一個 TTS 製作工具，讓你在腳本裡用標籤精確控制語速、停頓、說話風格、音效，以及互動式音色抽選（Gacha），最終輸出混音完成的音訊檔案。

---

## 目錄

1. [安裝](#安裝)
2. [設定 API](#設定-api)
3. [集中設定檔](#集中設定檔-aidenteconfigtoml)
4. [撰寫腳本](#撰寫腳本)
5. [標籤參考](#標籤參考)
6. [CLI 指令](#cli-指令)
7. [聲學屬性控制](#聲學屬性控制)
8. [音效（SFX）](#音效sfx)
9. [Gacha 互動選音](#gacha-互動選音)
10. [廣播劇製作範例](#廣播劇製作範例)
11. [錯誤排除](#錯誤排除)

---

## 安裝

需求：Python 3.11+、[uv](https://docs.astral.sh/uv/)、ffmpeg

```bash
brew install ffmpeg   # macOS
uv sync
```

---

## 設定 API

### 端點說明

| 端點 | 說明 |
|------|------|
| `/custom-voice` | 使用預設音色（**推薦**） |
| `/voice-design` | 用自然語言描述音色特質（不指定角色） |

```bash
export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"

# 永久生效
echo 'export MODAL_TTS_URL="https://..."' >> ~/.zshrc && source ~/.zshrc
```

---

## 集中設定檔 `~/.aidente/config.toml`

把常用設定和角色音色預設存在設定檔，不需要每次都打 CLI 參數。工具啟動時自動讀取，檔案不存在也可正常運作。

```bash
mkdir -p ~/.aidente
touch ~/.aidente/config.toml
```

### 格式說明

```toml
# 全域設定
modal_tts_url = "https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"
default_profile = "narrator"   # 沒指定 --profile 時的預設
max_concurrent = 10
sfx_dir = "~/.aidente/sfx"
api_log = "~/.aidente/api_log.jsonl"   # 留空 ("") 可停用
# api_log = ""                          # ← 停用 API 日誌

# ── 角色音色預設 ──────────────────────────────────────
[profiles.narrator]
speaker = "Ryan"
language = "Chinese"
instruct = "沉穩的旁白，像在說故事，語速平緩"
description = "旁白"

[profiles.xiaoling]
speaker = "Vivian"
language = "Chinese"
instruct = "18歲少女，活潑開朗，情緒起伏大，容易緊張"
description = "主角 小靈"

[profiles.villain]
speaker = "Dylan"
language = "Chinese"
instruct = "冷酷反派，說話緩慢有壓迫感，每個詞都充滿威脅"
description = "反派 暗影"

[profiles.grandma]
speaker = "Serena"
language = "Chinese"
instruct = "溫柔慈祥的老婆婆，說話緩慢輕柔，帶著一絲憂慮"
description = "奶奶"
```

### CLI 使用

```bash
# 使用設定檔指定的 default_profile
uv run aidente-voice generate -i script.txt

# 指定角色
uv run aidente-voice generate -i script.txt --profile villain

# CLI 參數覆蓋 profile（仍套用 profile 的其他設定）
uv run aidente-voice generate -i script.txt --profile xiaoling --instruct "today she is exhausted, speaking sluggishly"
```

---

## 撰寫腳本

腳本是純文字檔（`.txt`）。`。！？` 或換行自動切分成語音片段，標籤放在句子**後面**控制該句屬性。

```
今天天氣真好。
我們慢慢說吧。<speed=0.8>
<pause=1.5>
你竟然敢這樣對我！<style=very angry, shouting>
沒關係，我知道了。<style=whisper, resigned>
```

---

## 標籤參考

### `<pause=秒數>`

插入靜音。

```
準備好了嗎？<pause=2>那我們開始。
```

---

### `<speed=倍率>`

調整**前一句**語速。

```
慢慢說清楚。<speed=0.7>
快點！快點！<speed=1.5>
```

| 值 | 效果 |
|----|------|
| `0.5` | 極慢（半速） |
| `0.8` | 稍慢 |
| `1.0` | 正常 |
| `1.3` | 稍快 |
| `2.0` | 極快（倍速） |

> 支援範圍 `0.1` ～ `5.0`。不能獨立存在，必須接在句子後面。

---

### `<style=描述>`

控制**前一句**的說話風格、情緒、語調。透過 Qwen3-TTS 的 `instruct` 欄位實現。

```
平靜地說話。
我再也不想見到你！<style=very angry, shouting>
對不起，是我的錯。<style=apologetic, voice breaking>
哈哈哈，太好笑了！<style=laughing, joyful>
他……他不見了。<style=voice trembling with fear, barely audible>
```

**Qwen3-TTS 支援的聲學屬性：**

| 屬性類型 | 範例描述 |
|----------|---------|
| 情緒 | `happy`、`sad`、`angry`、`excited`、`nervous`、`disappointed` |
| 說話方式 | `whisper`、`shouting`、`laughing`、`crying`、`sighing` |
| 語速 | `very slow`、`fast`、`rushed`、`dragging each word` |
| 音調 | `high pitch`、`low and deep`、`monotone`、`rising intonation` |
| 角色風格 | `like a news anchor`、`like a child`、`like a villain` |
| 複合描述 | `speak slowly with trembling voice, as if about to cry` |

> **合併規則：** `<style=...>` 逐句標籤會與 `--instruct` 全域設定**合併**（`全域; 逐句`），讓模型同時看到兩者。

---

### `<voice=角色名稱>`

切換**前一句**使用的音色 profile（需在 `config.toml` 中定義）。

```
就在這時，旁白緩緩說道。<voice=narrator>
「你以為你能逃出我的掌心嗎？」<voice=villain>
小靈顫抖著回答：「我……我不怕你！」<style=terrified but defiant><voice=xiaoling>
```

> 不設定時沿用預設 profile 或 CLI 指定的音色。

---

### `<sfx=音效名[,fade=秒數]>`

插入音效。

```
<sfx=laugh>
<sfx=applause,fade=0.3>
```

---

### `<gacha=N>`

對**前一句**合成 N 個音色變體，讓你互動選擇。

```
這句台詞我想多試幾種感覺。<gacha=4>
```

可搭配 `<style=...>` 使用：

```
又哭又笑，情緒很複雜。<gacha=3><style=crying and laughing at the same time, conflicted>
```

---

## CLI 指令

### `aidente-voice generate`

```bash
uv run aidente-voice generate -i <腳本路徑> [選項]
```

#### 基本選項

| 選項 | 預設 | 說明 |
|------|------|------|
| `-i / --input` | **必填** | 輸入腳本路徑 |
| `-o / --output` | `output.wav` | 輸出路徑 |
| `--dry-run` | `false` | 只顯示解析結果，不呼叫 API |
| `--keep-chunks` | `false` | 保留個別片段到 `./chunks/` |
| `--max-concurrent` | `10` | 最大同時合成請求數 |
| `--sfx-dir` | `~/.aidente/sfx` | 音效目錄 |

#### 音色選項

| 選項 | 預設 | 說明 |
|------|------|------|
| `--profile` | config 的 `default_profile` | 使用 config.toml 定義的角色 profile |
| `--speaker` | `Ryan` | 預設音色（覆蓋 profile） |
| `--language` | `Auto` | 語言提示（覆蓋 profile） |
| `--instruct` | 無 | 全域說話風格，與 `<style=...>` 合併 |
| `--voice-design` | 無 | 改用 `/voice-design` 端點，值為音色描述 |

**可選音色（`--speaker`）：**

| 音色 | 特性 |
|------|------|
| `Ryan`（預設） | 成熟男聲 |
| `Aiden` | 年輕男聲 |
| `Dylan` | 低沉男聲 |
| `Eric` | 中性男聲 |
| `Ono_anna` | 日系女聲 |
| `Serena` | 成熟女聲 |
| `Vivian` | 活潑女聲 |
| `Sohee` | 韓系女聲 |
| `Uncle_fu` | 老者男聲 |

**可選語言（`--language`）：**
`Auto`、`Chinese`、`English`、`Japanese`、`Korean`、`French`、`German`、`Spanish`、`Portuguese`、`Russian`

#### 日誌選項

| 選項 | 預設 | 說明 |
|------|------|------|
| `--api-log` | `~/.aidente/api_log.jsonl` | API 紀錄路徑 |
| `--no-api-log` | `false` | 停用 API 紀錄 |

---

## 聲學屬性控制

### 層級 1：config.toml profile 預設風格

在設定檔定義好角色的說話基調。

### 層級 2：全域風格（`--instruct`）

整份腳本覆蓋 profile 的 instruct：

```bash
uv run aidente-voice generate -i script.txt \
  --profile xiaoling \
  --instruct "today she is very tired, speaking sluggishly"
```

### 層級 3：逐句風格（`<style=...>`）

與全域 instruct **合併**，不是覆蓋：

```
正常說話。
你怎麼可以這樣！<style=very angry, shouting>
```

### 音色設計模式（`--voice-design`）

不使用預設音色，直接描述你想要的聲音。注意：音色設計不選角色，只靠描述定義聲音特質。

```bash
uv run aidente-voice generate -i script.txt \
  --voice-design "A slightly husky narrator, mid-40s male, speaking with gravitas and warmth"
```

---

## 音效（SFX）

`.wav` 格式，放在 `~/.aidente/sfx/`（或 `--sfx-dir` 指定目錄）。工具自動重新取樣為 24kHz 單聲道。

```bash
mkdir -p ~/.aidente/sfx
cp laugh.wav ~/.aidente/sfx/
```

---

## Gacha 互動選音

腳本有 `<gacha=N>` 時，工具先合成所有普通語音，再逐一進入選音介面。

```
[Gacha] Chunk 2: '這句台詞我想多試幾種感覺。'
  Variants: 3 | Keys: 1-3 to play, Enter to confirm, q to quit
```

| 按鍵 | 動作 |
|------|------|
| `1` ～ `N` | 試聽對應變體 |
| `Enter` | 確認（若未試聽，自動播第一個） |
| `q` | 使用第一個變體 |

---

## 廣播劇製作範例

以下以一段廣播劇小品示範完整工作流程。

### 第一步：設定 config.toml

```toml
# ~/.aidente/config.toml
modal_tts_url = "https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"
default_profile = "narrator"

[profiles.narrator]
speaker = "Ryan"
language = "Chinese"
instruct = "沉穩的旁白，像在說故事，語速平緩"
description = "旁白"

[profiles.xiaoling]
speaker = "Vivian"
language = "Chinese"
instruct = "18歲少女，活潑開朗，情緒起伏大，容易緊張"
description = "主角 小靈"

[profiles.villain]
speaker = "Dylan"
language = "Chinese"
instruct = "冷酷反派，說話緩慢有壓迫感，每個詞都充滿威脅"
description = "反派 暗影"

[profiles.grandma]
speaker = "Serena"
language = "Chinese"
instruct = "溫柔慈祥的老婆婆，說話緩慢輕柔，帶著一絲憂慮"
description = "奶奶"
```

### 第二步：撰寫腳本 `ep01.txt`

```
黃昏時分，古老的祠堂前，小靈獨自等待著。<voice=narrator>
<sfx=wind>
「奶奶說過，這裡有能實現願望的神明……」<style=murmuring to herself, hopeful><voice=xiaoling>
<pause=0.8>
「真是個可愛的孩子。」<style=cold, amused, slightly mocking><voice=villain>
<sfx=footsteps>
小靈猛地轉身，心臟幾乎跳出胸口。<voice=narrator>
「你……你是誰！」<style=startled, terrified but trying to sound brave><voice=xiaoling>
「我叫暗影。」<style=low, deliberate, each word heavy with menace><speed=0.85><voice=villain>
<pause=0.5>
「你的願望——」<style=dangerously soft><voice=villain>
「讓我來幫你實現。」<style=cold smile in voice><voice=villain>
<pause=1.0>
<sfx=thunder>
小靈退後一步，腦海中突然浮現奶奶的叮嚀。<voice=narrator>
「千萬不要輕易許願……」<style=gentle, worried, echoing like a memory><voice=grandma>
```

### 第三步：先 Dry Run 確認解析

```bash
uv run aidente-voice generate -i ep01.txt --dry-run
```

輸出：
```
[DRY RUN] Parsed 16 chunks:
  [0]  tts    "黃昏時分，古老的祠堂前，小靈獨自等待著。" voice='narrator'
  [1]  sfx    wind fade=0.05
  [2]  tts    "「奶奶說過，這裡有能實現願望的神明……」" style='murmuring to herself, hopeful' voice='xiaoling'
  [3]  pause  0.8s
  [4]  tts    "「真是個可愛的孩子。」" style='cold, amused, slightly mocking' voice='villain'
  [5]  sfx    footsteps fade=0.05
  [6]  tts    "小靈猛地轉身，心臟幾乎跳出胸口。" voice='narrator'
  [7]  tts    "「你……你是誰！」" style='startled, terrified but trying to sound brave' voice='xiaoling'
  [8]  tts    "「我叫暗影。」" style='low, deliberate, each word heavy with menace' speed=0.85 voice='villain'
  [9]  pause  0.5s
  [10] tts    "「你的願望——」" style='dangerously soft' voice='villain'
  [11] tts    "「讓我來幫你實現。」" style='cold smile in voice' voice='villain'
  [12] pause  1.0s
  [13] sfx    thunder fade=0.05
  [14] tts    "小靈退後一步，腦海中突然浮現奶奶的叮嚀。" voice='narrator'
  [15] tts    "「千萬不要輕易許願……」" style='gentle, worried, echoing like a memory' voice='grandma'
No API calls made.
```

### 第四步：正式合成

```bash
uv run aidente-voice generate -i ep01.txt -o ep01.wav
```

### 第五步：保留各片段（方便後製）

```bash
uv run aidente-voice generate -i ep01.txt -o ep01.wav --keep-chunks
# 個別片段儲存在 ./chunks/
ls chunks/
# chunk_000_tts.wav  chunk_002_tts.wav  chunk_004_tts.wav ...
```

### 第六步：某句效果不理想？用 Gacha 重錄

```
「你……你是誰！」<style=startled, terrified but trying to sound brave><gacha=4><voice=xiaoling>
```

```bash
uv run aidente-voice generate -i ep01.txt -o ep01.wav
# 合成完畢後進入互動介面：
# [Gacha] Chunk 7: '「你……你是誰！」'
#   Variants: 4 | Keys: 1-4 to play, Enter to confirm, q to quit
# > 試聽各版本後按 Enter 確認
```

---

## 錯誤排除

### `MODAL_TTS_URL environment variable not set`

```bash
export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"
# 或在 config.toml 設定 modal_tts_url = "..."
```

### `Profile 'xxx' not found in config.toml`

確認 `~/.aidente/config.toml` 中有對應的 `[profiles.xxx]` 區塊。

### `ParseError: <voice> tag has no preceding sentence`

`<voice>` 必須接在句子後面：
```
# ❌
<voice=narrator> 接下來說道。

# ✅
接下來說道。<voice=narrator>
```

### `ParseError: <style> tag has no preceding sentence`

同上，`<style>` 也必須接在句子後面：
```
# ❌
<style=angry> 你竟敢！

# ✅
你竟敢！<style=angry, shouting>
```

### `ParseError: <speed> tag has no preceding sentence`

同上，`<speed>` 也必須接在句子後面。

### API 422 錯誤

確認 `--speaker` 值在允許清單內：
`Aiden, Dylan, Eric, Ono_anna, Ryan, Serena, Sohee, Uncle_fu, Vivian`

### 音效找不到

```bash
ls ~/.aidente/sfx/   # 確認檔案存在且名稱吻合
```
