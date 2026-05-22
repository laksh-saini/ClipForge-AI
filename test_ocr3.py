import easyocr
import glob
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
reader = easyocr.Reader(['en'])
frames = sorted(glob.glob("/tmp/ocr_test/frame_*.jpg"))

for frame in frames:
    results1 = reader.readtext(frame, text_threshold=0.1, low_text=0.1)
    res_text1 = [t[1] for t in results1]
    if res_text1:
        print(f"Frame {frame.split('/')[-1]}: {res_text1}")

