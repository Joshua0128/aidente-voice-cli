# aidente-voice 使用手冊

aidente-voice 是一個 TTS 製作工具，讓你在腳本裡用標籤精確控制語速、停頓、說話風格、音效，以及互動式音色抽選（Gacha），最終輸出混音完成的音訊檔案。

---

## 目錄

1. [安裝](#安裝)
2. [設定 API](#設定-api)
3. [撰寫腳本](#撰寫腳本)
4. [標籤參考](#標籤參考)
5. [CLI 指令](#cli-指令)
6. [聲學屬性控制](#聲學屬性控制)
7. [音效（SFX）](#音效sfx)
8. [Gacha 互動選音](#gacha-互動選音)
9. [常見用法範例](#常見用法範例)
10. [錯誤排除](#錯誤排除)

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
| `/voice-design` | 用自然語言描述音色特質 |

```bash
export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"

# 永久生效
echo 'export MODAL_TTS_URL="https://..."' >> ~/.zshrc && source ~/.zshrc
```

---

## 撰寫腳本

腳本是純文字檔（`.txt`）。日文 `。！？` 或換行自動切分成語音片段，標籤放在句子**後面**控制該句屬性。

```
こんにちは。
少しゆっくり話します。<speed=0.8>
<pause=1.5>
怒りながら叫ぶ！<style=very angry, shouting>
そっと囁く。<style=whisper, intimate>
```

---

## 標籤參考

### `<pause=秒數>`

插入靜音。

```
準備はよろしいですか。<pause=2>では、始めましょう。
```

---

### `<speed=倍率>`

調整**前一句**語速。

```
ゆっくり話す。<speed=0.7>
早口で話す。<speed=1.5>
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
普通に話す。
怒りながら叫ぶ！<style=very angry, shouting>
そっと囁く。<style=whisper, slow, intimate>
笑いながら話す。<style=laughing, joyful>
震える声で。<style=voice trembling with fear, barely audible>
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

> **優先級：** `<style=...>` 逐句標籤 > `--instruct` 全域設定。
> 每句可獨立設定，不設定的句子沿用全域 `--instruct`（若有）。

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
この台詞は何度も録り直したい。<gacha=4>
```

可搭配 `<style=...>` 使用：

```
怒りながら笑う複雑な表情。<gacha=3><style=angry yet laughing, conflicted>
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
| `--speaker` | `Ryan` | 預設音色 |
| `--language` | `Auto` | 語言提示 |
| `--instruct` | 無 | 全域說話風格（可被 `<style=...>` 逐句覆蓋） |
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

---

## 聲學屬性控制

Qwen3-TTS 的 `instruct` 欄位支援自然語言描述，本工具提供兩個層級：

### 層級 1：全域風格（`--instruct`）

整份腳本的預設風格：

```bash
uv run aidente-voice generate -i script.txt \
  --speaker Serena \
  --instruct "Speak slowly and warmly, like a caring teacher"
```

### 層級 2：逐句風格（`<style=...>`）

覆蓋特定句子的風格：

```
# script.txt
普通に話す。
怒りながら叫ぶ！<style=very angry, shouting>
冷静に戻る。
```

### 組合使用

```bash
# 全域：溫柔說話
# 但腳本中指定的句子會有自己的風格
uv run aidente-voice generate -i script.txt \
  --speaker Ono_anna \
  --language Japanese \
  --instruct "warm and gentle"
```

```
# script.txt
いつもありがとう。              ← 溫柔（全域）
なんでそんなこと言うの！<style=hurt and tearful>  ← 覆蓋
また明日ね。                    ← 溫柔（全域）
```

### 用描述設計全新音色（`--voice-design`）

不使用預設音色，直接描述你想要的聲音：

```bash
uv run aidente-voice generate -i script.txt \
  --voice-design "A young enthusiastic male developer, slightly sarcastic but friendly, mid-range voice"
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
[Gacha] Chunk 2: '怒りながら笑う複雑な表情。'
  Variants: 3 | Keys: 1-3 to play, Enter to confirm, q to quit
```

| 按鍵 | 動作 |
|------|------|
| `1` ～ `N` | 試聽對應變體 |
| `Enter` | 確認（若未試聽，自動播第一個） |
| `q` | 使用第一個變體 |

---

## 常見用法範例

### Dry run（確認解析結果）

```bash
uv run aidente-voice generate -i script.txt --dry-run
# 輸出：
# [DRY RUN] Parsed 4 chunks:
#   [0] tts    "普通に話す。"
#   [1] tts    "怒りながら叫ぶ！" style='very angry, shouting'
#   [2] pause  1.5s
#   [3] tts    "そっと囁く。" style='whisper, intimate'
```

### 基本合成

```bash
uv run aidente-voice generate -i script.txt -o output.wav
```

### 逐句情緒控制

```bash
# script.txt:
# 今日はいい天気ですね。
# なんで遅刻したの！<style=angry, sharp tone>
# ...ごめんなさい。<style=apologetic, quiet>

uv run aidente-voice generate -i script.txt --speaker Serena --language Japanese
```

### 全域 + 逐句組合

```bash
uv run aidente-voice generate -i script.txt \
  --speaker Ono_anna \
  --instruct "calm and professional" \
  --language Japanese
# 個別 <style=...> 標籤會覆蓋 "calm and professional"
```

### 音色設計模式

```bash
uv run aidente-voice generate -i script.txt \
  --voice-design "A slightly husky narrator, mid-40s male, speaking with gravitas and warmth"
```

---

## 錯誤排除

### `MODAL_TTS_URL environment variable not set`
```bash
export MODAL_TTS_URL="https://waiting-hchs--qwen3-tts-qwen3tts-api.modal.run/custom-voice"
```

### `ParseError: <style> tag has no preceding sentence`
`<style>` 必須接在句子後面，不能獨立存在：
```
# ❌
<style=angry> 叫ぶ！

# ✅
叫ぶ！<style=angry, shouting>
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
