from flask import Flask, render_template, request, jsonify
import os
import subprocess
import threading
import json
import sys
import platform
import glob
import traceback

app = Flask(__name__)
progress = {'status': 'ready', 'message': '', 'output_dir': None}
OUTPUT_FOLDER = 'processed_videos'


def update_progress(message, status=None):
    global progress
    progress['message'] = message
    if status:
        progress['status'] = status


def get_output_directory(input_path):
    """智能判断输出目录位置"""
    input_path = os.path.abspath(input_path)

    # 情况1：如果输入路径本身包含json文件，则输出到上级目录
    if any(f.lower().endswith('.json') for f in os.listdir(input_path)):
        parent_dir = os.path.dirname(input_path)
        if os.path.exists(parent_dir):
            return os.path.join(parent_dir, OUTPUT_FOLDER)

    # 情况2：如果输入路径的子目录包含json文件，则输出到同级目录
    for root, dirs, files in os.walk(input_path):
        if any(f.lower().endswith('.json') for f in files):
            return os.path.join(input_path, OUTPUT_FOLDER)

    # 情况3：默认输出到输入目录的同级目录
    return os.path.join(os.path.dirname(input_path), OUTPUT_FOLDER)


def strip_m4s_header(path):
    try:
        with open(path, 'rb') as f:
            content = f.read()
        if content[:9] == b'000000000':
            with open(path, 'wb') as f:
                f.write(content[9:])
            return content[:9]
        return b''
    except Exception as e:
        update_progress(f"文件处理错误: {str(e)}", "error")
        return b''


def restore_m4s_header(path, header):
    if not header:
        return
    try:
        with open(path, 'rb') as f:
            content = f.read()
        with open(path, 'wb') as f:
            f.write(header + content)
    except Exception as e:
        update_progress(f"文件恢复错误: {str(e)}", "error")


def process_single_video(full_path, mp4_dir, idx, total):
    try:
        # 查找所有json文件（支持多个json文件的情况）
        json_files = glob.glob(os.path.join(full_path, '*.json'))
        if not json_files:
            update_progress(f"{idx}/{total}：跳过 - 无 .json 文件")
            return None

        # 使用第一个找到的json文件
        json_path = json_files[0]
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        group_name = data.get('groupTitle', 'unknown').replace('/', '_').replace('\\', '_')
        group_path = os.path.join(mp4_dir, group_name)
        os.makedirs(group_path, exist_ok=True)

        name = data.get('title', 'video').replace('/', '_').replace('\\', '_')
        if name != group_name and 'p' in data:
            name = f"[{data['p']}]{name}"
        output_path = os.path.join(group_path, f"{name}.mp4")

        # 检查输出文件是否已存在
        if os.path.exists(output_path):
            update_progress(f"{idx}/{total}：已存在，跳过 - {name}")
            return False

        update_progress(f"{idx}/{total}：处理中 - {name}")

        # 查找所有m4s文件
        m4s_files = glob.glob(os.path.join(full_path, '*.m4s'))
        if len(m4s_files) < 2:
            update_progress(f"{idx}/{total}：跳过 - 文件不完整 (找到 {len(m4s_files)} 个m4s文件)")
            return None

        # 识别视频和音频文件
        video_file = next((f for f in m4s_files if 'video' in os.path.basename(f).lower()), None)
        audio_file = next((f for f in m4s_files if 'audio' in os.path.basename(f).lower()), None)

        # 如果通过关键字找不到，尝试通过大小判断（视频文件通常更大）
        if not video_file or not audio_file:
            # 按文件大小排序
            m4s_files.sort(key=os.path.getsize, reverse=True)
            video_file = m4s_files[0]  # 最大的文件假定为视频
            audio_file = m4s_files[1]  # 第二大的文件假定为音频
            update_progress(f"{idx}/{total}：使用大小推断视频/音频文件")

        # 获取FFmpeg路径
        ffmpeg_path = 'ffmpeg'
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
            # 检查不同平台的可执行文件
            if platform.system() == 'Windows':
                ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')
            else:
                ffmpeg_path = os.path.join(base_path, 'ffmpeg')

        # 处理文件头
        video_header = strip_m4s_header(video_file)
        audio_header = strip_m4s_header(audio_file)

        # 使用FFmpeg合并视频
        try:
            cmd = [
                ffmpeg_path,
                '-y',  # 覆盖输出文件
                '-i', video_file,
                '-i', audio_file,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-movflags', '+faststart',
                output_path
            ]

            # 显示更详细的错误信息
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=True
            )
            update_progress(f"{idx}/{total}：成功处理 - {name}")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = f"{idx}/{total}：合并失败 - {name}\n命令: {' '.join(cmd)}\n错误: {e.output if e.output else str(e)}"
            update_progress(error_msg, "error")
            return None
        finally:
            # 恢复文件头
            restore_m4s_header(video_file, video_header)
            restore_m4s_header(audio_file, audio_header)

    except Exception as e:
        error_msg = f"{idx}/{total}：异常 - {str(e)}\n{traceback.format_exc()}"
        update_progress(error_msg, "error")
        return None


def process_directory(base_dir):
    try:
        base_dir = os.path.abspath(os.path.normpath(base_dir))
        if not os.path.exists(base_dir):
            update_progress(f"目录不存在: {base_dir}", "error")
            return None

        # 获取输出目录
        mp4_dir = get_output_directory(base_dir)
        os.makedirs(mp4_dir, exist_ok=True)
        progress['output_dir'] = mp4_dir

        update_progress(f"输出目录: {mp4_dir}")

        # 扫描所有可能包含视频的子目录
        video_dirs = []
        for root, dirs, files in os.walk(base_dir):
            # 跳过输出目录
            if os.path.basename(root) == OUTPUT_FOLDER:
                continue

            # 检查是否有JSON文件
            if any(f.lower().endswith('.json') for f in files):
                video_dirs.append(root)

        update_progress(f"找到 {len(video_dirs)} 个视频目录")

        # 如果没有找到任何视频目录，返回错误
        if not video_dirs:
            update_progress("未找到任何视频目录（需要包含.json文件）", "error")
            return None

        # 处理所有找到的视频目录
        total = len(video_dirs)
        count = 0
        for idx, video_dir in enumerate(video_dirs, start=1):
            result = process_single_video(video_dir, mp4_dir, idx, total)
            if result is True:
                count += 1
            elif result is None:
                update_progress(f"{idx}/{total}：跳过无效目录: {video_dir}")

        update_progress(f"处理完成！成功处理 {count}/{total} 个视频", "completed")
        return mp4_dir

    except Exception as e:
        error_msg = f"处理失败: {str(e)}\n{traceback.format_exc()}"
        update_progress(error_msg, "error")
        return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process():
    input_dir = request.form['directory']
    progress['status'] = 'processing'
    progress['message'] = "正在扫描目录..."
    progress['output_dir'] = None

    def process_task():
        try:
            output_dir = process_directory(input_dir)
            if output_dir:
                progress['output_dir'] = output_dir
        except Exception as e:
            progress['status'] = 'error'
            progress['message'] = f"处理失败: {str(e)}"

    threading.Thread(target=process_task).start()
    return jsonify(progress)


@app.route('/progress')
def get_progress():
    return jsonify(progress)


@app.route('/open_output', methods=['POST'])
def open_output():
    try:
        # 获取并验证输出目录
        output_path = progress.get('output_dir')
        if not output_path:
            return jsonify({
                'success': False,
                'message': '输出目录未设置',
                'detail': '请先完成视频处理流程'
            }), 400

        # 规范化路径并检查存在性
        output_path = os.path.abspath(os.path.normpath(output_path))
        if not os.path.exists(output_path):
            return jsonify({
                'success': False,
                'message': '输出目录不存在',
                'detail': f'路径: {output_path}'
            }), 404

        # 根据操作系统执行打开命令
        system_os = platform.system()
        try:
            if system_os == 'Windows':
                # Windows使用explorer，添加start命令确保非阻塞
                subprocess.Popen(
                    ['start', 'explorer', output_path],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            elif system_os == 'Darwin':  # macOS
                subprocess.Popen(
                    ['open', output_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            elif system_os == 'Linux':
                subprocess.Popen(
                    ['xdg-open', output_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                return jsonify({
                    'success': False,
                    'message': '不支持的操作系统',
                    'detail': system_os
                }), 501

            return jsonify({
                'success': True,
                'message': '目录已打开',
                'path': output_path
            })

        except subprocess.SubprocessError as e:
            app.logger.error(f"打开目录失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': '打开目录命令执行失败',
                'detail': str(e)
            }), 500

    except Exception as e:
        app.logger.exception("打开目录时发生意外错误")
        return jsonify({
            'success': False,
            'message': '服务器内部错误',
            'detail': str(e)
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
