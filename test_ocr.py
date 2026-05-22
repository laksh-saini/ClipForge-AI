import easyocr
import glob
import os
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
reader = easyocr.Reader(['en'])
images = glob.glob("/Users/lakshsaini/.gemini/antigravity/brain/9713dc29-c7aa-4a56-a790-31c7a6355e2f/*.png")
for img in images:
    print(f"--- {img} ---")
    results = reader.readtext(img)
    for bbox, text, prob in results:
        print(f"[{prob:.2f}] {text}")

