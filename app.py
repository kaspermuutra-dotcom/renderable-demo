from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import uuid
from PIL import Image
import io

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

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
    
    filename = f'angle_{angle}.jpg'
    file.save(os.path.join(scan_folder, filename))
    
    return jsonify({'scan_id': scan_id, 'angle': angle, 'status': 'saved'})

@app.route('/stitch/<scan_id>', methods=['POST'])
def stitch(scan_id):
    scan_folder = os.path.join(UPLOAD_FOLDER, scan_id)
    if not os.path.exists(scan_folder):
        return jsonify({'error': 'Scan not found'}), 404
    
    photos = sorted([f for f in os.listdir(scan_folder) if f.endswith('.jpg') and f != 'panorama.jpg'])
    
    if len(photos) == 0:
        return jsonify({'error': 'No photos found'}), 400
    
    images = []
    for photo in photos:
        img = Image.open(os.path.join(scan_folder, photo))
        images.append(img)
    
    target_height = 1080
    resized = []
    for img in images:
        ratio = target_height / img.height
        new_width = int(img.width * ratio)
        resized.append(img.resize((new_width, target_height), Image.LANCZOS))
    
    total_width = sum(img.width for img in resized)
    panorama = Image.new('RGB', (total_width, target_height))
    
    x_offset = 0
    for img in resized:
        panorama.paste(img, (x_offset, 0))
        x_offset += img.width
    
    panorama_path = os.path.join(scan_folder, 'panorama.jpg')
    panorama.save(panorama_path, quality=85)
    
    return jsonify({'scan_id': scan_id, 'status': 'stitched', 'url': f'/photos/{scan_id}/panorama.jpg'})

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
    photos = sorted([f for f in photos if f.endswith('.jpg') and f != 'panorama.jpg'])
    return jsonify({'photos': photos, 'has_panorama': has_panorama})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=True)