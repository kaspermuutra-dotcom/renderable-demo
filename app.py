from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import uuid
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import io

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/instructions')
def instructions():
    return render_template('instructions.html')

@app.route('/capture')
def capture():
    return render_template('capture.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo'}), 400
    file = request.files['photo']
    scan_id = request.form.get('scan_id', str(uuid.uuid4()))
    angle = request.form.get('angle', '0')
    scan_folder = os.path.join(UPLOAD_FOLDER, scan_id)
    os.makedirs(scan_folder, exist_ok=True)
    filename = f'angle_{int(float(angle)):03d}.jpg'
    file.save(os.path.join(scan_folder, filename))
    return jsonify({'scan_id': scan_id, 'angle': angle, 'status': 'saved'})

@app.route('/stitch/<scan_id>', methods=['POST'])
def stitch(scan_id):
    scan_folder = os.path.join(UPLOAD_FOLDER, scan_id)
    if not os.path.exists(scan_folder):
        return jsonify({'error': 'Scan not found'}), 404

    photos = sorted([
        f for f in os.listdir(scan_folder)
        if f.startswith('angle_') and f.endswith('.jpg')
    ])

    if len(photos) < 2:
        return jsonify({'error': 'Not enough photos'}), 400

    images = []
    for photo in photos:
        try:
            img = Image.open(os.path.join(scan_folder, photo)).convert('RGB')
            images.append(img)
        except:
            pass

    if len(images) < 2:
        return jsonify({'error': 'Could not load images'}), 400

    target_h = 2048
    resized = []
    for img in images:
        ratio = target_h / img.height
        new_w = int(img.width * ratio)
        resized.append(img.resize((new_w, target_h), Image.LANCZOS))

    overlap = resized[0].width // 5
    total_w = sum(img.width for img in resized) - overlap * (len(resized) - 1)
    panorama = Image.new('RGB', (total_w, target_h))

    x = 0
    for i, img in enumerate(resized):
        w = img.width
        if i == 0:
            panorama.paste(img, (0, 0))
            x = w - overlap
        else:
            blend_region_left = np.array(panorama.crop((x, 0, x + overlap, target_h)), dtype=np.float32)
            blend_region_right = np.array(img.crop((0, 0, overlap, target_h)), dtype=np.float32)
            mask = np.linspace(1, 0, overlap, dtype=np.float32).reshape(1, -1, 1)
            mask = np.repeat(mask, target_h, axis=0)
            blended = (blend_region_left * mask + blend_region_right * (1 - mask)).astype(np.uint8)
            blended_img = Image.fromarray(blended)
            panorama.paste(blended_img, (x, 0))
            panorama.paste(img.crop((overlap, 0, w, target_h)), (x + overlap, 0))
            x += w - overlap

    final_w = 4096
    final_h = 2048
    final = panorama.resize((final_w, final_h), Image.LANCZOS)
    enhancer = ImageEnhance.Sharpness(final)
    final = enhancer.enhance(1.2)

    panorama_path = os.path.join(scan_folder, 'panorama.jpg')
    final.save(panorama_path, quality=88, optimize=True)

    return jsonify({
        'scan_id': scan_id,
        'status': 'stitched',
        'url': f'/photos/{scan_id}/panorama.jpg'
    })

@app.route('/view/<scan_id>')
def view(scan_id):
    return render_template('viewer.html', scan_id=scan_id)

@app.route('/photos/<scan_id>/<filename>')
def get_photo(scan_id, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, scan_id), filename)

@app.route('/scans/<scan_id>')
def get_scan_photos(scan_id):
    scan_folder = os.path.join(UPLOAD_FOLDER, scan_id)
    if not os.path.exists(scan_folder):
        return jsonify({'photos': [], 'has_panorama': False})
    photos = os.listdir(scan_folder)
    has_panorama = 'panorama.jpg' in photos
    photos = sorted([f for f in photos if f.startswith('angle_') and f.endswith('.jpg')])
    return jsonify({'photos': photos, 'has_panorama': has_panorama})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=True)