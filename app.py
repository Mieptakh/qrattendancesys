import os
import qrcode
import pandas as pd
from flask import Flask, render_template, request, flash, redirect, url_for, send_file, session, jsonify
from flask_cors import CORS
from datetime import datetime
from PIL import Image
from pyzbar.pyzbar import decode
import cv2
import time

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

def get_csv_filename():
    date_str = datetime.now().strftime('%Y-%m-%d')
    return f'detected_qr_codes_{date_str}.csv'

def init_csv():
    csv_filename = get_csv_filename()
    if not os.path.exists(csv_filename):
        detected_qr_codes_df = pd.DataFrame(columns=['qr_code', 'timestamp'])
        detected_qr_codes_df.to_csv(csv_filename, index=False)
        print(f"Created '{csv_filename}' with columns: qr_code, timestamp")

def get_detected_qr_codes_df():
    csv_filename = get_csv_filename()
    if os.path.exists(csv_filename):
        return pd.read_csv(csv_filename)
    return pd.DataFrame(columns=['qr_code', 'timestamp'])

def save_detected_qr_codes_df(df):
    csv_filename = get_csv_filename()
    df.to_csv(csv_filename, index=False)

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('user_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == 'admin' and password == 'admin1234':
            session['logged_in'] = True
            session['role'] = 'admin'
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        elif username == 'user' and password == 'user1234':
            session['logged_in'] = True
            session['role'] = 'user'
            flash('Login successful!', 'success')
            return redirect(url_for('user_dashboard'))
        flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/admin-dashboard')
def admin_dashboard():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html')

@app.route('/user-dashboard')
def user_dashboard():
    if not session.get('logged_in') or session.get('role') != 'user':
        return redirect(url_for('login'))
    return render_template('user_dashboard.html')

@app.route('/generate', methods=['GET', 'POST'])
def generate():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if session.get('role') == 'admin':
        if request.method == 'POST':
            names_str = request.form['names']
            class_name = request.form['class']
            absen_start = int(request.form['absen_start'])

            names = [name.strip() for name in names_str.split(',') if name.strip()]

            if not names:
                flash('Names cannot be empty.', 'danger')
                return redirect(url_for('generate'))

            qr_code_dir = 'static/qrcodes'
            os.makedirs(qr_code_dir, exist_ok=True)

            for i, name in enumerate(names):
                absen = absen_start + i
                qr_data = f"{name} - {class_name} - {absen}"
                qr_code_path = os.path.join(qr_code_dir, f"{name.replace(' ', '_')}.png")

                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=20,  # Increased box size for higher resolution
                    border=4,
                )
                qr.add_data(qr_data)
                qr.make(fit=True)

                # Use custom colors for the QR code
                qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')

                qr_img.save(qr_code_path)

            flash('Custom QR Codes successfully generated!', 'success')
            return render_template('generate.html', generated=True, names=names)

        available_classes = ['10A', '10B', '10C', '12 IPA 1', '12 IPA 2', '12 IPS 1', '12 IPS 2']
        return render_template('generate.html', available_classes=available_classes, is_admin=True)

    elif session.get('role') == 'user':
        if request.method == 'POST':
            name = request.form['name']
            class_name = request.form['class']
            absen = request.form['absen']

            if not name:
                flash('Name cannot be empty.', 'danger')
                return redirect(url_for('generate'))

            qr_code_dir = 'static/qrcodes'
            os.makedirs(qr_code_dir, exist_ok=True)

            qr_data = f"{name} - {class_name} - {absen}"
            qr_code_path = os.path.join(qr_code_dir, f"{name.replace(' ', '_')}.png")

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=20,  # Increased box size for higher resolution
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            # Use custom colors for the QR code
            qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')

            qr_img.save(qr_code_path)

            flash('Custom QR Code successfully generated!', 'success')
            return render_template('generate.html', generated=True, name=name)

        available_classes = ['10A', '10B', '10C', '12 IPA 1', '12 IPA 2', '12 IPS 1', '12 IPS 2']
        return render_template('generate.html', available_classes=available_classes)

@app.route('/scan', methods=['GET', 'POST'])
def scan():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            flash('Could not open webcam.', 'error')
            return redirect(url_for('admin_dashboard'))

        time.sleep(2)
        cv2.namedWindow('Scan QR Code', cv2.WINDOW_AUTOSIZE)

        try:
            detected_qr_codes_df = get_detected_qr_codes_df()
            scanned_qr_codes = set(detected_qr_codes_df['qr_code'].tolist())

            valid_qr_codes = set()
            qr_code_dir = 'static/qrcodes'
            for filename in os.listdir(qr_code_dir):
                if filename.endswith('.png'):
                    qr_code_path = os.path.join(qr_code_dir, filename)
                    with Image.open(qr_code_path) as img:
                        decoded_objects = decode(img)
                        for obj in decoded_objects:
                            valid_qr_codes.add(obj.data.decode('utf-8'))

            while True:
                ret, frame = cap.read()
                if not ret:
                    flash('Failed to capture image.', 'error')
                    break
                
                decoded_objects = decode(frame)
                for obj in decoded_objects:
                    qr_code_data = obj.data.decode('utf-8')
                    print(f"Detected QR code data: {qr_code_data}")

                    if qr_code_data in valid_qr_codes and qr_code_data not in scanned_qr_codes:
                        now = datetime.now()
                        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')

                        new_row = pd.DataFrame({'qr_code': [qr_code_data], 'timestamp': [timestamp]})
                        detected_qr_codes_df = pd.concat([detected_qr_codes_df, new_row], ignore_index=True)
                        save_detected_qr_codes_df(detected_qr_codes_df)

                        scanned_qr_codes.add(qr_code_data)
                        flash('QR code scanned successfully!', 'success')
                    
                    break

                cv2.imshow('Scan QR Code', frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        
        finally:
            cap.release()
            cv2.destroyAllWindows()

        return redirect(url_for('admin_dashboard'))

    return render_template('scan.html')

@app.route('/export', methods=['GET'])
def export():
    detected_qr_codes_df = get_detected_qr_codes_df()
    export_path = get_csv_filename()
    save_detected_qr_codes_df(detected_qr_codes_df)
    
    return send_file(export_path, as_attachment=True)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('role', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_csv()
    app.run(host='0.0.0.0', debug=True)