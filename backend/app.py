import re
from flask import Flask, request, jsonify, send_from_directory
import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import cv2
import threading
import time

# Tesseract path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# 🔥 AUTO DELETE
def delete_file_later(path, delay=15):  # increased delay for safety
    def delete():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=delete).start()


# 🔍 DETECTION
def detect_sensitive_data(text):
    text = text.replace("\n", " ").upper()
    results = {}

    # Aadhaar
    aadhaar = re.findall(r'\b\d{12}\b|\b\d{4}\s?\d{4}\s?\d{4}\b', text)
    if aadhaar:
        results["Aadhaar"] = aadhaar

    # PAN
    pan = re.findall(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', text)
    if pan:
        results["PAN"] = pan

    # Phone
    phone = re.findall(r'\b\d{10}\b', text)
    if phone:
        results["Phone"] = phone

    # Card
    card = re.findall(r'\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b', text)
    if card:
        results["Card"] = card

    # Passport simple
    passport = re.findall(r'\b[A-Z][0-9]{7}\b', text)
    if passport:
        results["Passport"] = passport

    # 🔥 MRZ (passport / visa)
    mrz = re.findall(r'[A-Z0-9<]{20,}', text)
    if mrz:
        results["Passport_MRZ"] = mrz

    return results


# 🧾 TEXT MASKING
def mask_sensitive_data(text, detected):
    for key in detected:
        for value in detected[key]:
            clean = value.replace(" ", "")

            if len(clean) >= 12:
                masked = clean[:4] + " XXXX XXXX"
            else:
                masked = "XXXX"

            text = text.replace(value, masked)

    return text


# 🖼️ IMAGE MASKING
def mask_image(filepath, detected_values):
    img = cv2.imread(filepath)

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    n = len(data['text'])

    chunks = []
    for value in detected_values:
        clean = value.replace(" ", "")
        chunks.extend([clean[i:i+4] for i in range(0, len(clean), 4)])

    for i in range(n):
        word = data['text'][i]

        for chunk in chunks:
            if chunk and chunk in word:
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]

                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), -1)

    output_filename = "masked_" + os.path.basename(filepath)
    output_path = os.path.join(UPLOAD_FOLDER, output_filename)

    cv2.imwrite(output_path, img)

    return output_filename


# 📷 SERVE IMAGE
@app.route('/image/<filename>')
def get_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/')
def home():
    return "Backend running 🚀"


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    filename = file.filename.lower()

    try:
        if filename.endswith('.pdf'):
            images = convert_from_path(
                filepath,
                poppler_path=r'C:\Users\vikas\Downloads\Release-25.12.0-0\poppler-25.12.0\Library\bin',
                dpi=200,
                first_page=1,
                last_page=1
            )

            text = ""
            for img in images:
                text += pytesseract.image_to_string(img)

        elif filename.endswith(('.png', '.jpg', '.jpeg')):
            image = Image.open(filepath)
            text = pytesseract.image_to_string(image)
            image.close()

        else:
            return jsonify({"error": "Unsupported file type"}), 400

    except Exception as e:
        text = str(e)

    # 🔍 Detect
    detected = detect_sensitive_data(text)

    # 🧾 Mask text
    masked_text = mask_sensitive_data(text, detected)

    # 🖼️ Mask image
    all_values = []
    for key in detected:
        all_values.extend(detected[key])

    masked_filename = None
    masked_path = None

    if filename.endswith(('.png', '.jpg', '.jpeg')) and all_values:
        masked_filename = mask_image(filepath, all_values)
        masked_path = os.path.join(UPLOAD_FOLDER, masked_filename)

    # 🔥 AUTO DELETE (delayed)
    delete_file_later(filepath)

    if masked_path:
        delete_file_later(masked_path)

    return jsonify({
        "message": "Processed successfully",
        "detected_data": detected,
        "masked_text": masked_text,
        "masked_image_url": f"http://127.0.0.1:5000/image/{masked_filename}" if masked_filename else None
    })


if __name__ == '__main__':
    app.run(debug=True)