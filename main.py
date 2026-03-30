"""
clap_launcher.py — Double-clap to launch Claude Code
Launches Windows Terminal maximized with 3 panes: claude | copilot | gemini
Plays clip.mp3 via pygame. Mic detection paused until the exact
WindowsTerminal.exe PID spawned by this script exits.

Requirements: pip install pyaudio numpy pygame
Windows Terminal (wt.exe) must be installed.
"""

import time
import os
import subprocess
import threading
import numpy as np
import pyaudio
import pygame
from welcome_script import WELCOME_SCRIPT, WELCOME_SCRIPT_PATH

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK = 1024
RATE = 44100
THRESHOLD = 2500  # RMS volume to count as a clap (tune to your mic)
CLAP_WINDOW = 0.8  # Max seconds between two claps
COOLDOWN = 2.0  # Seconds to ignore after launch
WT_SPAWN_WAIT = (
    2.0  # Seconds to wait for WindowsTerminal.exe to appear after wt.exe runs
)
POLL_INTERVAL = 1.5  # How often (seconds) to check if the PID is still alive
VSCODE_DIR = r"C:\\Users\\chris\\Desktop\\VSCodes"


subprocess.run(["code", "--trust", VSCODE_DIR])

# ── Globals ───────────────────────────────────────────────────────────────────

terminal_locked = False
lock = threading.Lock()

# ── pygame init ───────────────────────────────────────────────────────────────

pygame.mixer.init()

# ── Helpers ───────────────────────────────────────────────────────────────────


def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def play_mp3():
    """Play clip.mp3 in a daemon thread via pygame."""
    mp3_path = os.path.join(get_script_dir(), "clip.mp3")
    if not os.path.exists(mp3_path):
        print(f"[warn] clip.mp3 not found at {mp3_path}, skipping audio.")
        return

    def _play():
        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

    threading.Thread(target=_play, daemon=True).start()


def get_wt_pids_before():
    """Snapshot all running WindowsTerminal.exe PIDs right now."""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq WindowsTerminal.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
    )
    pids = set()
    for line in result.stdout.strip().splitlines():
        parts = line.strip().strip('"').split('","')
        if len(parts) >= 2:
            try:
                pids.add(int(parts[1]))
            except ValueError:
                pass
    return pids


def pid_is_alive(pid):
    """Return True if a process with this PID is still running."""
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
    )
    return str(pid) in result.stdout


def launch_terminal():
    """
    Launch a fullscreen welcome screen with TTS, then Windows Terminal maximized with 3 vertical panes.
    Returns the PID of the new WindowsTerminal.exe process, or None if not found.
    """
    # Write welcome script fresh each time
    with open(WELCOME_SCRIPT_PATH, "w", encoding="utf-8") as f:
        f.write(WELCOME_SCRIPT)

    pids_before = get_wt_pids_before()

    # Step 1: Launch welcome screen
    welcome_cmd = [
        "wt.exe",
        "--maximized",
        "new-tab",
        "--title",
        "Welcome",
        "cmd.exe",
        "/k",
        WELCOME_SCRIPT_PATH,
    ]
    subprocess.Popen(
        welcome_cmd, shell=False, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )

    # Step 2: Wait for TTS + welcome screen to finish (speech ~2s + art + 3s timeout)
    time.sleep(6)

    # Step 3: Launch the actual 3-pane terminal
    cmd = [
        "wt.exe",
        "--maximized",
        "new-tab",
        "--title",
        "Claude",
        "--startingDirectory",
        VSCODE_DIR,
        "cmd.exe",
        "/k",
        "claude",
        ";",
        "split-pane",
        "--vertical",
        "--size",
        "0.6667",
        "--title",
        "Copilot",
        "--startingDirectory",
        VSCODE_DIR,
        "cmd.exe",
        "/k",
        "copilot",
        ";",
        "split-pane",
        "--vertical",
        "--size",
        "0.5",
        "--title",
        "Gemini",
        "--startingDirectory",
        VSCODE_DIR,
        "cmd.exe",
        "/k",
        "gemini",
    ]
    subprocess.Popen(
        cmd, shell=False, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )

    # Step 4: Detect the new WindowsTerminal PID (the 3-pane one)
    deadline = time.time() + WT_SPAWN_WAIT
    while time.time() < deadline:
        time.sleep(0.3)
        pids_after = get_wt_pids_before()
        new_pids = pids_after - pids_before
        if new_pids:
            pid = max(new_pids)
            print(f"WindowsTerminal.exe started with PID {pid}")
            return pid

    print(
        "[warn] Could not detect WindowsTerminal.exe PID — lock will not release automatically."
    )
    return None


def monitor_terminal(pid):
    """Poll until the specific PID is gone, then release the mic lock."""
    global terminal_locked

    if pid is None:
        # Fallback: just wait a fixed time then release
        time.sleep(30)
        with lock:
            terminal_locked = False
        print("Lock released (fallback timeout).")
        return

    while pid_is_alive(pid):
        time.sleep(POLL_INTERVAL)

    with lock:
        terminal_locked = False
    print(f"WindowsTerminal.exe (PID {pid}) closed — mic detection re-enabled.")


def is_terminal_alive():
    with lock:
        return terminal_locked


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

        # Mic detection locked while terminal is open
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
                    with lock:
                        terminal_locked = True
                    pid = launch_terminal()
                    threading.Thread(
                        target=monitor_terminal, args=(pid,), daemon=True
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
    pygame.mixer.quit()
