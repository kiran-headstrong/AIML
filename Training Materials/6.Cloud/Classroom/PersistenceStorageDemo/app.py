import os
from flask import Flask, request, render_template, send_from_directory, redirect, url_for

app = Flask(__name__)

DATA_DIR = os.environ.get('DATA_DIR', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

@app.route('/')
def index():
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.txt')]
    return render_template('index.html', files=files)

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    if file and file.filename.endswith('.txt'):
        file.save(os.path.join(DATA_DIR, file.filename))
    return redirect(url_for('index'))

@app.route('/files/<filename>')
def get_file(filename):
    return send_from_directory(DATA_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
