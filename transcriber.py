import os
import sys
import io
import time
import wave
import threading
import winsound
import ctypes

# Один экземпляр: если уже запущен — тихо выходим
_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "TranscribrApp_SingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)

import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
import pystray
from PIL import Image, ImageDraw
from deepgram import DeepgramClient, PrerecordedOptions
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
HOTKEY = os.getenv("HOTKEY", "space")
HOLD_DELAY = float(os.getenv("HOLD_DELAY", "1.0"))
SAMPLE_RATE = 16000
MIN_RECORD_SEC = float(os.getenv("MIN_RECORD_SEC", "0.5"))


def _paste_via_winapi():
    """Ctrl+V через Windows SendInput, минуя библиотеку keyboard."""
    from ctypes import wintypes

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL = 0x11
    VK_V = 0x56

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("_u", _U)]

    def ki(vk, flags=0):
        return INPUT(type=INPUT_KEYBOARD, _u=_U(ki=KEYBDINPUT(wVk=vk, dwFlags=flags)))

    seq = (INPUT * 4)(
        ki(VK_CONTROL), ki(VK_V),
        ki(VK_V, KEYEVENTF_KEYUP), ki(VK_CONTROL, KEYEVENTF_KEYUP),
    )
    ctypes.windll.user32.SendInput(4, seq, ctypes.sizeof(INPUT))


def _make_icon(bg: tuple, dot: bool = False) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], fill=bg)
    d.rounded_rectangle([26, 14, 38, 40], radius=6, fill="white")
    d.arc([18, 36, 46, 52], 180, 0, fill="white", width=3)
    d.line([32, 52, 32, 58], fill="white", width=3)
    d.line([26, 58, 38, 58], fill="white", width=3)
    if dot:
        d.ellipse([44, 4, 60, 20], fill=(255, 80, 80))
    return img


ICON_IDLE = _make_icon((60, 175, 80))
ICON_REC  = _make_icon((30, 30, 30), dot=True)
ICON_BUSY = _make_icon((70, 120, 210))


class Transcriber:
    def __init__(self):
        self.is_recording = False
        self.is_processing = False
        self.frames: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.tray: pystray.Icon | None = None
        self._rec_start: float = 0.0
        self._lock = threading.Lock()
        self._hold_timer: threading.Timer | None = None

    # ── горячая клавиша ───────────────────────────────────────────────────────

    def _on_key(self, event: keyboard.KeyboardEvent):
        if event.event_type == keyboard.KEY_DOWN:
            with self._lock:
                if not self.is_recording and not self.is_processing and self._hold_timer is None:
                    self._hold_timer = threading.Timer(HOLD_DELAY, self._on_hold_triggered)
                    self._hold_timer.start()
        elif event.event_type == keyboard.KEY_UP:
            with self._lock:
                if self._hold_timer is not None:
                    self._hold_timer.cancel()
                    self._hold_timer = None
                if self.is_recording:
                    self._stop()

    def _on_hold_triggered(self):
        with self._lock:
            self._hold_timer = None
            if not self.is_recording and not self.is_processing:
                self._start()

    # ── запись ────────────────────────────────────────────────────────────────

    def _start(self):
        self.frames = []
        self.is_recording = True
        self._rec_start = time.monotonic()
        self._set_icon(ICON_REC, "Транскрибатор — запись...")
        winsound.Beep(880, 80)

        def _cb(indata, *_):
            if self.is_recording:
                self.frames.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=_cb
        )
        self.stream.start()

    def _stop(self):
        self.is_recording = False
        duration = time.monotonic() - self._rec_start

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        winsound.Beep(440, 80)

        if not self.frames or duration < MIN_RECORD_SEC:
            self._set_icon(ICON_IDLE, "Транскрибатор")
            return

        self.is_processing = True
        self._set_icon(ICON_BUSY, "Транскрибатор — распознавание...")
        threading.Thread(target=self._transcribe, daemon=True).start()

    # ── транскрипция ──────────────────────────────────────────────────────────

    def _transcribe(self):
        try:
            audio = np.concatenate(self.frames, axis=0)

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio.tobytes())
            buf.seek(0)

            if GROQ_API_KEY:
                from groq import Groq
                client = Groq(api_key=GROQ_API_KEY)
                result = client.audio.transcriptions.create(
                    file=("audio.wav", buf.read()),
                    model="whisper-large-v3-turbo",
                    language="ru",
                    response_format="text",
                )
                text = (result if isinstance(result, str) else result.text).strip()
            else:
                client = DeepgramClient(DEEPGRAM_API_KEY)
                opts = PrerecordedOptions(
                    model="nova-2", language="ru",
                    smart_format=True, punctuate=True,
                )
                resp = client.listen.rest.v("1").transcribe_file(
                    {"buffer": buf.read(), "mimetype": "audio/wav"}, opts
                )
                text = resp.results.channels[0].alternatives[0].transcript.strip()

            if text:
                pyperclip.copy(text)
                time.sleep(0.15)
                _paste_via_winapi()
                winsound.Beep(1200, 80)
            else:
                winsound.Beep(600, 200)

        except Exception as exc:
            print(f"[Ошибка] {exc}", flush=True)
            winsound.Beep(300, 400)

        finally:
            self.is_processing = False
            self._set_icon(ICON_IDLE, "Транскрибатор")

    # ── трей ──────────────────────────────────────────────────────────────────

    def run(self):
        _win = ("windows", "win", "left windows", "right windows")
        _alt = ("alt", "left alt", "right alt")

        if HOTKEY.lower() in _win:
            hotkey_names = {"left windows", "right windows"}
        elif HOTKEY.lower() in _alt:
            hotkey_names = {"left alt", "right alt"}
        else:
            # символьные клавиши могут отображаться как сам символ или как слово
            hotkey_names = {HOTKEY.lower(), HOTKEY}

        def _global_hook(event: keyboard.KeyboardEvent):
            if event.name and event.name in hotkey_names:
                self._on_key(event)

        keyboard.hook(_global_hook, suppress=False)

        if "windows" in HOTKEY.lower():
            label = "Win"
        elif "alt" in HOTKEY.lower():
            label = "Alt"
        elif HOTKEY == ",":
            label = ","
        else:
            label = HOTKEY.upper()

        menu = pystray.Menu(
            pystray.MenuItem(
                f"Удерживайте [{label}] для записи",
                lambda *_: None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", lambda *_: self._quit()),
        )
        self.tray = pystray.Icon("transcriber", ICON_IDLE, "Транскрибатор", menu)
        self.tray.run()

    def _set_icon(self, icon: Image.Image, title: str):
        if self.tray:
            self.tray.icon = icon
            self.tray.title = title

    def _quit(self):
        if self.is_recording:
            with self._lock:
                self._stop()
        if self.tray:
            self.tray.stop()
        sys.exit(0)


if __name__ == "__main__":
    if not GROQ_API_KEY and not DEEPGRAM_API_KEY:
        print(
            "ОШИБКА: Укажите GROQ_API_KEY или DEEPGRAM_API_KEY в файле .env\n"
            "Шаблон: .env.example",
            file=sys.stderr,
        )
        sys.exit(1)
    Transcriber().run()
