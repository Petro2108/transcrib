# Transcrib — Voice-to-Text Tray App

Windows tray application that records speech via a hold-key hotkey and pastes the transcription into the focused window.

## Stack

- **Python 3.11+**
- **Deepgram nova-2** — speech recognition (Russian)
- **sounddevice** — microphone capture
- **keyboard** — global hotkey hook
- **pystray** — system tray icon
- **pyperclip + SendInput** — clipboard paste

## Key file

`transcriber.py` — entire app in one file.

## How it works

1. App starts → sits in tray (green mic icon).
2. User holds the hotkey for `HOLD_DELAY` seconds → recording starts (dark icon + red dot, high beep).
3. User releases hotkey → recording stops (low beep), audio sent to Deepgram API.
4. Transcribed text is copied to clipboard and pasted via `SendInput Ctrl+V` into whatever window had focus.

## Configuration (.env)

| Variable | Default | Notes |
|---|---|---|
| `DEEPGRAM_API_KEY` | — | Required. Get at console.deepgram.com |
| `HOTKEY` | `right ctrl` | Key to hold. Supports any `keyboard` lib name |
| `HOLD_DELAY` | `1.0` | Seconds of hold before recording starts |
| `MIN_RECORD_SEC` | `0.5` | Ignore recordings shorter than this |

## Hotkey notes

- Uses `keyboard.hook()` (global hook, suppress=False) — works without admin rights.
- Modifier keys like `right ctrl`, `left alt`, `left windows` work best — they produce no characters so the target window stays clean.
- Character keys (comma, space) cause auto-repeat flooding in the target window while held — avoid.

## Paste mechanism

`_paste_via_winapi()` uses raw `SendInput` instead of the keyboard library to avoid interference with the global hook. There is a 0.6 s sleep before paste to let the OS settle focus after recording ends.

## Single-instance guard

A named Windows Mutex (`TranscribrApp_SingleInstance`) prevents duplicate processes — a second launch exits silently.

## Running

```
pip install -r requirements.txt
cp .env.example .env   # add DEEPGRAM_API_KEY
python transcriber.py
```
