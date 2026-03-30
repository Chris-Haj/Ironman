"""
clap_launcher.py — Double-clap to launch Claude Code
Launches Windows Terminal maximized with 3 panes: claude | copilot | gemini
Plays clip.mp3 on launch. Mic detection paused while terminal is alive.

Requirements: pip install pyaudio numpy
Windows Terminal (wt.exe) must be installed.
"""

import time
import os
import subprocess
import threading
import numpy as np
import pyaudio

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK = 1024
RATE = 44100
THRESHOLD = 2500  # RMS volume to count as a clap (tune to your mic)
CLAP_WINDOW = 0.8  # Max seconds between two claps
COOLDOWN = 2.0  # Seconds to ignore after launch

# ── Globals ───────────────────────────────────────────────────────────────────

terminal_proc = None  # The wt.exe process
lock = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────


def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def play_mp3():
    """Play clip.mp3 using PowerShell's Windows Media Player (no extra deps)."""
    mp3_path = os.path.join(get_script_dir(), "clip.mp3")
    if not os.path.exists(mp3_path):
        print(f"[warn] clip.mp3 not found at {mp3_path}, skipping audio.")
        return

    # Escape backslashes for PowerShell string
    ps_path = mp3_path.replace("\\", "\\\\")
    ps_script = (
        f"$player = New-Object System.Windows.Media.MediaPlayer;"
        f"$player.Open([Uri]::new('{ps_path}'));"
        f"Start-Sleep -Milliseconds 500;"  # give it time to load
        f"$player.Play();"
        f"Start-Sleep -Seconds 10;"  # keep process alive while playing
        f"$player.Close()"
    )

    def _play():
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-Command",
                ps_script,
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    threading.Thread(target=_play, daemon=True).start()


def launch_terminal():
    """
    Launch Windows Terminal maximized with 3 vertical panes:
      left: claude | middle: copilot | right: gemini
    Returns the Popen process.
    """
    cmd = [
        "wt.exe",
        "--maximized",
        "new-tab",
        "--title",
        "Claude",
        "cmd.exe",
        "/k",
        "claude",
        ";",
        "split-pane",
        "--vertical",
        "--title",
        "Copilot",
        "cmd.exe",
        "/k",
        "copilot",
        ";",
        "split-pane",
        "--vertical",
        "--title",
        "Gemini",
        "cmd.exe",
        "/k",
        "gemini",
    ]
    return subprocess.Popen(
        cmd, shell=False, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )


def is_terminal_alive():
    global terminal_proc
    with lock:
        if terminal_proc is None:
            return False
        if terminal_proc.poll() is not None:
            terminal_proc = None
            return False
        return True


def monitor_terminal(proc):
    """Wait for wt.exe to exit, then re-enable mic detection."""
    global terminal_proc
    proc.wait()
    with lock:
        terminal_proc = None
    print("Terminal closed — mic detection re-enabled.")


# ── Audio setup ───────────────────────────────────────────────────────────────

pa = pyaudio.PyAudio()
stream = pa.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
)

# ── State ─────────────────────────────────────────────────────────────────────

last_clap_time = 0.0
last_launch_time = 0.0
in_clap = False

print("Listening for double-claps... (Ctrl+C to quit)")

# ── Main loop ─────────────────────────────────────────────────────────────────

try:
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))

        now = time.time()

        # Mic detection is locked while terminal session is alive
        if is_terminal_alive():
            in_clap = False
            continue

        if rms > THRESHOLD:
            if not in_clap:
                in_clap = True

                if now - last_launch_time < COOLDOWN:
                    pass  # still in cooldown
                elif now - last_clap_time < CLAP_WINDOW:
                    # Second clap within window → launch
                    print("Double-clap! Launching terminals...")
                    play_mp3()
                    proc = launch_terminal()
                    with lock:
                        terminal_proc = proc
                    threading.Thread(
                        target=monitor_terminal, args=(proc,), daemon=True
                    ).start()
                    last_launch_time = now
                    last_clap_time = 0.0
                else:
                    print("Clap 1 — waiting for second...")
                    last_clap_time = now
        else:
            in_clap = False

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
