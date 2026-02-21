import os
import uuid
import zipfile
import json
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from werkzeug.utils import secure_filename
from pydub import AudioSegment
import yt_dlp

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'ogg', 'flac', 'm4a', 'webm'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_folder():
    """Get or create session-specific folder"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    folder = os.path.join(app.config['OUTPUT_FOLDER'], session['session_id'])
    os.makedirs(folder, exist_ok=True)
    return folder


@app.route('/')
def index():
    """Main page - YouTube download and file upload"""
    # Clear previous session data for fresh start
    session.clear()
    get_session_folder()  # Initialize new session
    return render_template('index.html')


@app.route('/download_youtube', methods=['POST'])
def download_youtube():
    """Download audio from YouTube URLs"""
    data = request.get_json()
    urls = data.get('urls', [])

    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400

    session_folder = get_session_folder()
    downloaded_files = []
    errors = []

    for url in urls:
        if not url.strip():
            continue

        try:
            # Generate unique filename
            filename = f"youtube_{uuid.uuid4().hex[:8]}"
            output_path = os.path.join(session_folder, f"{filename}.wav")

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(session_folder, filename),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
                'quiet': False,
                'no_warnings': False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', filename)

            downloaded_files.append({
                'filename': f"{filename}.wav",
                'title': title,
                'original_url': url
            })

        except Exception as e:
            errors.append({'url': url, 'error': str(e)})

    return jsonify({
        'success': True,
        'downloaded': downloaded_files,
        'errors': errors
    })


@app.route('/upload_files', methods=['POST'])
def upload_files():
    """Upload audio files for trimming"""
    session_folder = get_session_folder()

    if 'files[]' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files[]')
    uploaded_files = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
            filepath = os.path.join(session_folder, unique_name)

            # Save original file
            file.save(filepath)

            # Convert to WAV if not already
            if not filename.lower().endswith('.wav'):
                audio = AudioSegment.from_file(filepath)
                wav_path = filepath.rsplit('.', 1)[0] + '.wav'
                audio.export(wav_path, format='wav')
                os.remove(filepath)
                unique_name = unique_name.rsplit('.', 1)[0] + '.wav'

            uploaded_files.append({
                'filename': unique_name,
                'original_name': filename
            })

    # Store uploaded files in session for trimming workflow
    session['files_to_trim'] = uploaded_files
    session['current_trim_index'] = 0
    session['all_trimmed_files'] = []

    return jsonify({
        'success': True,
        'files': uploaded_files,
        'redirect': url_for('trim_page', index=0)
    })


@app.route('/trim/<int:index>')
def trim_page(index):
    """Page for trimming a specific file"""
    files_to_trim = session.get('files_to_trim', [])

    if index < 0 or index >= len(files_to_trim):
        return redirect(url_for('download_page'))

    current_file = files_to_trim[index]
    session_folder = get_session_folder()
    filepath = os.path.join(session_folder, current_file['filename'])

    # Get audio duration
    audio = AudioSegment.from_file(filepath)
    duration = len(audio) / 1000  # in seconds

    return render_template('trim.html',
                           file=current_file,
                           index=index,
                           total=len(files_to_trim),
                           duration=duration)


@app.route('/get_audio/<filename>')
def get_audio(filename):
    """Serve audio file for playback"""
    session_folder = get_session_folder()
    return send_file(os.path.join(session_folder, filename))


@app.route('/trim_segment', methods=['POST'])
def trim_segment():
    """Trim a segment from current audio file"""
    data = request.get_json()
    filename = data.get('filename')
    start_time = float(data.get('start', 0))
    end_time = float(data.get('end', 0))
    output_name = data.get('output_name', '')

    session_folder = get_session_folder()
    filepath = os.path.join(session_folder, filename)

    # Load audio and trim
    audio = AudioSegment.from_file(filepath)
    start_ms = start_time * 1000
    end_ms = end_time * 1000
    trimmed = audio[start_ms:end_ms]

    # Generate output filename
    if not output_name:
        output_name = f"trimmed_{uuid.uuid4().hex[:8]}.wav"
    elif not output_name.endswith('.wav'):
        output_name += '.wav'

    output_path = os.path.join(session_folder, output_name)
    trimmed.export(output_path, format='wav')

    # Track trimmed file in session
    if 'all_trimmed_files' not in session:
        session['all_trimmed_files'] = []

    session['all_trimmed_files'].append({
        'filename': output_name,
        'source': filename,
        'start': start_time,
        'end': end_time
    })
    session.modified = True

    return jsonify({
        'success': True,
        'output_file': output_name
    })


@app.route('/next_file')
def next_file():
    """Move to next file for trimming or finish"""
    current_index = session.get('current_trim_index', 0)
    files_to_trim = session.get('files_to_trim', [])

    current_index += 1
    session['current_trim_index'] = current_index

    if current_index >= len(files_to_trim):
        return jsonify({'done': True, 'redirect': url_for('download_page')})

    return jsonify({
        'done': False,
        'redirect': url_for('trim_page', index=current_index)
    })


@app.route('/download')
def download_page():
    """Final page with download options - only trimmed files"""
    # Get only trimmed files from session
    trimmed_files = session.get('all_trimmed_files', [])
    files = [f['filename'] for f in trimmed_files]

    return render_template('download.html', files=files)


@app.route('/download_zip')
def download_zip():
    """Download all trimmed audio files as ZIP"""
    session_folder = get_session_folder()
    trimmed_files = session.get('all_trimmed_files', [])

    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], f"audio_export_{session['session_id']}.zip")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_info in trimmed_files:
            filename = file_info['filename']
            filepath = os.path.join(session_folder, filename)
            if os.path.exists(filepath):
                zipf.write(filepath, filename)

    return send_file(zip_path,
                     mimetype='application/zip',
                     as_attachment=True,
                     download_name='audio_export.zip')


@app.route('/delete_file', methods=['POST'])
def delete_file():
    """Delete a specific file from session folder"""
    data = request.get_json()
    filename = data.get('filename')

    session_folder = get_session_folder()
    filepath = os.path.join(session_folder, filename)

    if os.path.exists(filepath):
        os.remove(filepath)
        # Also remove from session list
        trimmed_files = session.get('all_trimmed_files', [])
        session['all_trimmed_files'] = [f for f in trimmed_files if f['filename'] != filename]
        session.modified = True
        return jsonify({'success': True})

    return jsonify({'error': 'File not found'}), 404


@app.route('/list_files')
def list_files():
    """List all files in session folder"""
    session_folder = get_session_folder()
    files = [f for f in os.listdir(session_folder) if f.endswith('.wav')]
    return jsonify({'files': files})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
