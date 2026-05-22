import subprocess
import glob
import easyocr
import ssl
import shutil
from pathlib import Path

ssl._create_default_https_context = ssl._create_unverified_context

video_path = "/Users/lakshsaini/Library/Application Support/com.clipforge.app/staged_media/Living_like_there_is_no_tomorrow______cinematic__sonyalpha__videography__traveltheworld__cinema_1779366214390_0.mp4"
temp_dir = Path("/tmp/ocr_test_crop")
if temp_dir.exists():
    shutil.rmtree(temp_dir)
temp_dir.mkdir()

# Extract center crop
cmd = [
    "ffmpeg", "-y", "-i", video_path,
    "-vf", "fps=4,crop=iw*0.8:ih*0.4:(iw-ow)/2:(ih-oh)/2",
    f"{temp_dir}/frame_%04d.jpg"
]
subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

reader = easyocr.Reader(['en'])
frames = sorted(temp_dir.glob("frame_*.jpg"))

all_text = []
for frame in frames:
    results = reader.readtext(str(frame), text_threshold=0.3, low_text=0.3)
    res_text = [t[1] for t in results if t[2] > 0.2]
    if res_text:
        all_text.append(f"{frame.name}: {res_text}")

print("Extracted Text with Crop:")
for t in all_text:
    print(t)
