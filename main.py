from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import re, os, requests
from video import get_video

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.getcwd(), 'downloads')


@app.route('/downloads/<path:filename>')
def downloads(filename):
    requested_path = os.path.abspath(os.path.join(DOWNLOAD_DIR, filename))
    if not requested_path.startswith(DOWNLOAD_DIR):
        abort(404)
    return send_from_directory(DOWNLOAD_DIR, filename)


@app.route('/', methods=['GET', 'POST'])
def index():
    input_data = None
    if request.method == 'POST':
        input_data = request.form.get('user_input')
    return render_template('index.html', input_data=input_data)


@app.route('/api/get_video', methods=['POST'])
def video_api():
    try:
        data = request.get_json()
        video_url = data.get('url')

        if not video_url:
            return jsonify({'error': '缺少视频URL参数'}), 400

        title = get_video(video_url)

        safe_title = re.sub(r'[\\/:"*?<>|]+', '', title)
        filename = f"{safe_title}.mp4"
        video_path = os.path.join(DOWNLOAD_DIR, filename)

        if not os.path.exists(video_path):
            return jsonify({'error': '视频文件不存在，合并可能失败'}), 500

        return jsonify({
            'title': title,
            'video_url': f'/downloads/{filename}'
        })

    except requests.RequestException as e:
        return jsonify({'error': f'请求B站失败: {str(e)}'}), 502
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)

