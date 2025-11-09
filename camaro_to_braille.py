#!/usr/bin/env python3
# camera_to_braille.py (Trixie-ready)
# - Capture from Pi camera (Picamera2 preferred; falls back to rpicam-still)
# - OCR via Tesseract (English)
# - Optional send to ESP32 over USB serial (chunked)

import os, sys, time, glob, subprocess
from typing import Optional
import cv2
import numpy as np
import serial
import pytesseract
from PIL import Image

# ---------------------- CONFIG ----------------------
RESOLUTION = (640, 480)          # Keep low for smooth preview over SSH/X11
SERIAL_BAUD = 115200
MAX_CHARS_PER_CHUNK = 120
CAPTURE_TIMEOUT_SEC = 6          # Auto-capture if user doesn't press 'c'
LANG = "eng"                     # OCR language
TESSERACT_CONFIG = "--oem 3 --psm 6"
SHOW_PREVIEW = True              # Auto-disabled if no DISPLAY
# ----------------------------------------------------

SHOW_PREVIEW = SHOW_PREVIEW and bool(os.environ.get("DISPLAY"))

# Prefer Picamera2; if not present, we'll fall back to rpicam-still CLI
try:
    from picamera2 import Picamera2
    PICAMERA2_OK = True
except Exception:
    PICAMERA2_OK = False

# Point pytesseract at the usual binary path (safe if it doesn't exist)
if os.path.exists("/usr/bin/tesseract"):
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

def checkpoint(msg: str) -> None:
    print(f"[OK] {msg}")

def find_serial_port() -> Optional[str]:
    cands = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    return cands[0] if cands else None

def send_to_esp32(text: str, port: Optional[str] = None) -> None:
    text = (text or "").strip()
    if not text:
        print("No text detected to send.")
        return
    if port is None:
        port = find_serial_port()
    if not port:
        print("No ESP32 serial port found (e.g., /dev/ttyACM0). Skipping send.")
        return
    print(f"Connecting to ESP32 on {port} @ {SERIAL_BAUD}…")
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=2) as ser:
            time.sleep(2)  # allow ESP32 auto-reset
            payload = " ".join(text.split())
            while payload:
                chunk = payload[:MAX_CHARS_PER_CHUNK]
                payload = payload[MAX_CHARS_PER_CHUNK:]
                ser.write(chunk.encode("utf-8") + b"\n")
                ser.flush()
                time.sleep(0.15)
        print("Sent to ESP32.")
    except Exception as e:
        print(f"Serial error: {e}")

def capture_with_picamera2() -> np.ndarray:
    """Capture a single frame with Picamera2 (with optional OpenCV preview)."""
    if not PICAMERA2_OK:
        raise RuntimeError("Picamera2 not available.")
    from picamera2 import Picamera2
    picam = Picamera2()
    config = picam.create_still_configuration({"size": RESOLUTION})
    picam.configure(config)
    picam.start()
    time.sleep(0.5)  # warm-up

    frame = None
    t0 = time.time()
    print(f"Press 'c' to capture, 'q' to quit. (Auto-captures in {CAPTURE_TIMEOUT_SEC} sec)")

    try:
        if SHOW_PREVIEW:
            while True:
                img = picam.capture_array()
                cv2.imshow("Camera (press c to capture)", img)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('c'):
                    frame = img
                    break
                if key == ord('q'):
                    cv2.destroyAllWindows()
                    sys.exit(0)
                if time.time() - t0 >= CAPTURE_TIMEOUT_SEC:
                    frame = img
                    print("(Auto-captured due to timeout)")
                    break
            cv2.destroyAllWindows()
        else:
            frame = picam.capture_array()
    finally:
        picam.stop()

    if frame is None:
        raise RuntimeError("Failed to capture frame with Picamera2.")
    return frame

def capture_with_rpicam() -> np.ndarray:
    """Capture via rpicam-still (CLI), no preview, then load with OpenCV."""
    # Use a temp file in the working directory
    tmp_path = "capture_rpicam.jpg"
    # Small exposure to avoid DMABUF preview issues over X11
    cmd = ["rpicam-still", "--nopreview", "-t", "1000", "-o", tmp_path, "--width", str(RESOLUTION[0]), "--height", str(RESOLUTION[1])]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise RuntimeError("rpicam-still not found. Install rpicam-apps, or use Picamera2.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"rpicam-still failed: {e.stderr.decode(errors='ignore') or e}")

    img = cv2.imread(tmp_path)
    if img is None:
        raise RuntimeError("Failed to load image captured by rpicam-still.")
    return img

def capture_frame() -> np.ndarray:
    """Try Picamera2 first; if unavailable, fall back to rpicam-still."""
    if PICAMERA2_OK:
        try:
            return capture_with_picamera2()
        except Exception as e:
            print(f"Picamera2 capture failed ({e}); falling back to rpicam-still…")
    # Fallback to rpicam
    return capture_with_rpicam()

def preprocess_for_ocr(img_bgr: np.ndarray) -> np.ndarray:
    """Light denoise + threshold for better OCR."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    # OTSU works well; switch to adaptive if lighting is very uneven
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def ocr_image(np_img: np.ndarray) -> str:
    pil_img = Image.fromarray(np_img)
    try:
        text = pytesseract.image_to_string(pil_img, lang=LANG, config=TESSERACT_CONFIG)
    except Exception as e:
        print(f"OCR error: {e}")
        text = ""
    return text

def main() -> None:
    checkpoint("Starting capture…")
    frame = capture_frame()
    cv2.imwrite("capture_raw.jpg", frame)
    checkpoint("Saved capture_raw.jpg")

    proc = preprocess_for_ocr(frame)
    cv2.imwrite("capture_proc.jpg", proc)
    checkpoint("Saved capture_proc.jpg")

    text = ocr_image(proc)
    checkpoint("OCR complete")
    print("\n===== OCR RESULT =====")
    print(text if text.strip() else "(no text detected)")
    print("======================\n")

    choice = input("Send to ESP32? [y/N]: ").strip().lower()
    if choice == "y":
        checkpoint("Sending to ESP32…")
        send_to_esp32(text)
        checkpoint("Send complete")
    else:
        print("Skipped sending.")

if __name__ == "__main__":
    main()