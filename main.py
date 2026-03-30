"""
clap_launcher.py — Double-clap to launch Claude Code
Requirements: pip install pyaudio numpy
"""

import time
import numpy as np
import subprocess
import pyaudio
import webbrowser

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK = 1024  # Audio frames per buffer
RATE = 44100  # Sample rate (Hz)
THRESHOLD = 2500  # RMS volume to count as a clap (raise if too sensitive)
CLAP_WINDOW = 0.8  # Max seconds between two claps to count as a double-clap
COOLDOWN = 2.0  # Seconds to ignore input after launching
process = None  # holds the launched process
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
in_clap = False  # Tracks whether we're mid-clap (prevents counting one clap twice)

print("Listening for double-claps... (Ctrl+C to quit)")

# ── Main loop ─────────────────────────────────────────────────────────────────

try:
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))

        now = time.time()

        if rms > THRESHOLD:
            if not in_clap:
                in_clap = True

                if now - last_launch_time < COOLDOWN:
                    pass  # still in cooldown, ignore
                elif now - last_clap_time < CLAP_WINDOW:
                    # Second clap detected within window → launch!
                    print("Double-clap detected! Launching Claude Code...")
                    subprocess.Popen(
                        ["cmd.exe", "/c", "start", "cmd.exe", "/k", "claude"],
                        shell=False,
                    )
                    webbrowser.open("https://www.youtube.com/watch?v=BN1WwnEDWAM")

                    last_launch_time = now
                    last_clap_time = 0.0  # reset so next gesture starts fresh
                else:
                    # First clap
                    print("Clap 1 detected, waiting for second...")
                    last_clap_time = now
        else:
            in_clap = False  # Volume dropped — ready to detect next clap

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
