import re
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import cv2

# ⚠️ SET PATHS
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
POPPLER_PATH = r'C:\Users\vikas\Downloads\Release-25.12.0-0\poppler-25.12.0\Library\bin'

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# 🔍 DETECT
def detect_sensitive_data(text):
    patterns = [
        r'\b\d{12}\b',
        r'\b\d{4}\s?\d{4}\s?\d{4}\b',
        r'\b[A-Z]{5}[0-9]{4}[A-Z]\b',
        r'\b\d{10}\b'
    ]
    found = []
    for p in patterns:
        found += re.findall(p, text)
    return list(set(found))


# 🖼️ MASK IMAGE
def mask_image(filepath, values):
    img = cv2.imread(filepath)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    chunks = []
    for v in values:
        clean = v.replace(" ", "")
        chunks += [clean[i:i+4] for i in range(0, len(clean), 4)]

    for i in range(len(data['text'])):
        word = data['text'][i]
        for chunk in chunks:
            if chunk and chunk in word:
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                cv2.rectangle(img, (x,y), (x+w,y+h), (0,0,0), -1)

    out = "masked_" + os.path.basename(filepath)
    out_path = os.path.join(UPLOAD_FOLDER, out)
    cv2.imwrite(out_path, img)

    return out


# 📷 PREVIEW
@app.route('/image/<filename>')
def image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ⬇ DOWNLOAD
@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


@app.route('/')
def home():
    return "Backend running 🚀"


# 🖼 IMAGE API
@app.route('/upload-image', methods=['POST'])
def upload_image():
    try:
        file = request.files['file']
        path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(path)

        text = pytesseract.image_to_string(Image.open(path))
        detected = detect_sensitive_data(text)

        masked = mask_image(path, detected) if detected else None

        return jsonify({
            "image": f"http://127.0.0.1:5000/image/{masked}",
            "download": f"http://127.0.0.1:5000/download/{masked}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 📄 PDF API
@app.route('/upload-pdf', methods=['POST'])
def upload_pdf():
    try:
        file = request.files['file']
        path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(path)

        images = convert_from_path(path, poppler_path=POPPLER_PATH)

        masked_imgs = []

        for i, img in enumerate(images):
            temp = os.path.join(UPLOAD_FOLDER, f"temp_{i}.png")
            img.save(temp)

            text = pytesseract.image_to_string(img)
            detected = detect_sensitive_data(text)

            masked_name = mask_image(temp, detected)
            masked_imgs.append(Image.open(os.path.join(UPLOAD_FOLDER, masked_name)))

        pdf_path = os.path.join(UPLOAD_FOLDER, "masked.pdf")
        masked_imgs[0].save(pdf_path, save_all=True, append_images=masked_imgs[1:])

        return jsonify({
            "download": "http://127.0.0.1:5000/download/masked.pdf"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)