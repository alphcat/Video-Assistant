from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import re, os, requests
from video import get_video
import time
from moviepy.editor import VideoFileClip
import hashlib

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.getcwd(), 'downloads')
# 确保下载目录存在
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 用于跟踪视频片段的字典
video_segments = {}

# 视频缓存
video_cache = {}

def get_video_hash(url):
    """生成视频URL的哈希值作为缓存键"""
    return hashlib.md5(url.encode()).hexdigest()

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
        input_data = {
            'url': request.form.get('user_input'),
            'start': request.form.get('start_time'),
            'end': request.form.get('end_time')
        }
    return render_template('index.html', input_data=input_data)

@app.route('/api/preview_video', methods=['POST'])
def preview_video():
    try:
        data = request.get_json()
        video_url = data.get('url')

        if not video_url:
            return jsonify({'error': '缺少视频URL参数'}), 400

        # 检查缓存
        video_hash = get_video_hash(video_url)
        if video_hash in video_cache:
            return jsonify(video_cache[video_hash])

        # 获取视频信息
        title = get_video(video_url)
        safe_title = re.sub(r'[\\/:"*?<>|]+', '', title)
        filename = f"{safe_title}.mp4"
        video_path = os.path.join(DOWNLOAD_DIR, filename)

        if not os.path.exists(video_path):
            return jsonify({'error': '视频文件不存在'}), 500

        # 初始化视频片段跟踪
        if safe_title not in video_segments:
            video_segments[safe_title] = {
                'original_path': video_path,
                'segments': []
            }

        response_data = {
            'title': title,
            'video_url': f'/downloads/{filename}'
        }

        # 更新缓存
        video_cache[video_hash] = response_data

        return jsonify(response_data)

    except requests.RequestException as e:
        return jsonify({'error': f'请求B站失败: {str(e)}'}), 502
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/get_segments', methods=['POST'])
def get_segments():
    try:
        data = request.get_json()
        title = data.get('title')
        safe_title = re.sub(r'[\\/:"*?<>|]+', '', title)

        if safe_title not in video_segments:
            return jsonify({'segments': []})

        segments = []
        for segment in video_segments[safe_title]['segments']:
            # 从文件名中提取时间信息
            filename = os.path.basename(segment)
            time_match = re.search(r'_(\d+)-(\d+)_', filename)
            if time_match:
                start_time = float(time_match.group(1))
                end_time = float(time_match.group(2))
                segments.append({
                    'title': title,
                    'start': start_time,
                    'end': end_time,
                    'url': f'/downloads/{os.path.basename(segment)}'
                })

        return jsonify({'segments': segments})

    except Exception as e:
        return jsonify({'error': f'获取片段列表失败: {str(e)}'}), 500

@app.route('/api/finish_download', methods=['POST'])
def finish_download():
    try:
        data = request.get_json()
        title = data.get('title')
        safe_title = re.sub(r'[\\/:"*?<>|]+', '', title)

        if safe_title not in video_segments:
            return jsonify({'error': '未找到视频信息'}), 404

        video_info = video_segments[safe_title]
        if os.path.exists(video_info['original_path']):
            try:
                os.remove(video_info['original_path'])
                print(f"完成当前下载，点击重置继续下载: {video_info['original_path']}")
            except Exception as e:
                return jsonify({'error': f'删除原始视频失败: {str(e)}'}), 500

        # 清理缓存和片段记录
        if safe_title in video_segments:
            del video_segments[safe_title]
        
        # 清理视频缓存
        for url_hash, cache_data in list(video_cache.items()):
            if cache_data.get('title') == title:
                del video_cache[url_hash]

        return jsonify({'message': '完成当前下载，点击重置继续下载'})

    except Exception as e:
        return jsonify({'error': f'操作失败: {str(e)}'}), 500

@app.route('/api/get_video', methods=['POST'])
def video_api():
    try:
        data = request.get_json()
        video_url = data.get('url')
        start_time = data.get('start')
        end_time = data.get('end')

        if not video_url:
            return jsonify({'error': '缺少视频URL参数'}), 400

        # 检查缓存
        video_hash = get_video_hash(video_url)
        cached_data = video_cache.get(video_hash, {})

        title = cached_data.get('title') or get_video(video_url)
        safe_title = re.sub(r'[\\/:"*?<>|]+', '', title)
        original_filename = f"{safe_title}.mp4"
        video_path = os.path.join(DOWNLOAD_DIR, original_filename)

        if not os.path.exists(video_path):
            return jsonify({'error': '视频文件不存在，合并可能失败'}), 500

        # 处理时间段剪辑
        if start_time and end_time:
            try:
                # 生成剪辑后文件名（带时间戳防冲突）
                clip_filename = f"{safe_title}_{start_time}-{end_time}_{int(time.time())}.mp4"
                clip_path = os.path.join(DOWNLOAD_DIR, clip_filename)
                
                # 使用MoviePy剪辑视频，优化参数
                clip = VideoFileClip(video_path)
                edited_clip = clip.subclip(float(start_time), float(end_time))
                edited_clip.write_videofile(
                    clip_path,
                    codec="libx264",
                    audio_codec="aac",
                    threads=4,
                    fps=clip.fps,
                    preset='ultrafast',  # 使用最快的编码预设
                    ffmpeg_params=['-crf', '28']  # 使用较高的压缩率
                )
                clip.close()
                final_filename = clip_filename

                # 记录视频片段
                if safe_title not in video_segments:
                    video_segments[safe_title] = {
                        'original_path': video_path,
                        'segments': []
                    }
                video_segments[safe_title]['segments'].append(clip_path)

                # 获取所有片段信息
                segments = []
                for segment in video_segments[safe_title]['segments']:
                    filename = os.path.basename(segment)
                    time_match = re.search(r'_(\d+)-(\d+)_', filename)
                    if time_match:
                        start = float(time_match.group(1))
                        end = float(time_match.group(2))
                        segments.append({
                            'title': title,
                            'start': start,
                            'end': end,
                            'url': f'/downloads/{filename}'
                        })

                return jsonify({
                    'title': title,
                    'video_url': f'/downloads/{final_filename}',
                    'segments': segments
                })

            except Exception as e:
                return jsonify({'error': f'视频剪辑失败: {str(e)}'}), 500
        else:
            return jsonify({
                'title': title,
                'video_url': f'/downloads/{original_filename}'
            })

    except requests.RequestException as e:
        return jsonify({'error': f'请求B站失败: {str(e)}'}), 502
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)

