from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import uuid
import cv2
import numpy as np
from PIL import Image
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
        img = cv2.imread(os.path.join(scan_folder, photo))
        if img is not None:
            images.append(img)
    
    if len(images) < 2:
        return jsonify({'error': 'Could not load images'}), 400

    panorama_path = os.path.join(scan_folder, 'panorama.jpg')

    try:
        stitcher = cv2.Stitcher.create(cv2.Stitcher_PANORAMA)
        stitcher.setPanoConfidenceThresh(0.3)
        status, pano = stitcher.stitch(images)
        
        if status == cv2.Stitcher_OK:
            h, w = pano.shape[:2]
            target_w = max(w, 4096)
            target_h = target_w // 2
            equirect = cv2.resize(pano, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
            cv2.imwrite(panorama_path, equirect, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return jsonify({'scan_id': scan_id, 'status': 'stitched', 'url': f'/photos/{scan_id}/panorama.jpg'})
        else:
            return fallback_stitch(images, panorama_path, scan_id)
            
    except Exception as e:
        return fallback_stitch(images, panorama_path, scan_id)

def fallback_stitch(images, panorama_path, scan_id):
    try:
        target_h = 2048
        resized = []
        for img in images:
            ratio = target_h / img.shape[0]
            new_w = int(img.shape[1] * ratio)
            resized.append(cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_LANCZOS4))
        
        total_w = sum(img.shape[1] for img in resized)
        panorama = np.zeros((target_h, total_w, 3), dtype=np.uint8)
        
        x = 0
        for img in resized:
            w = img.shape[1]
            overlap = w // 8
            if x > 0 and x + w <= total_w:
                for c in range(overlap):
                    alpha = c / overlap
                    panorama[:, x+c] = (
                        (1 - alpha) * panorama[:, x+c] + 
                        alpha * img[:, c]
                    ).astype(np.uint8)
                panorama[:, x+overlap:x+w] = img[:, overlap:]
            else:
                panorama[:, x:x+w] = img
            x += w - overlap // 2

        final_w = 4096
        final_h = 2048
        final = cv2.resize(panorama[:, :x], (final_w, final_h), interpolation=cv2.INTER_LANCZOS4)
        cv2.imwrite(panorama_path, final, [cv2.IMWRITE_JPEG_QUALITY, 88])
        
        return jsonify({'scan_id': scan_id, 'status': 'stitched_fallback', 'url': f'/photos/{scan_id}/panorama.jpg'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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