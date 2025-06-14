# -*- coding: utf-8 -*-
import requests
import re
import json
import subprocess
import os
import time


def merge_av(audio_file, video_file, output_file):
    """
    合并音频和视频文件
    :param audio_file: 音频文件路径
    :param video_file: 视频文件路径
    :param output_file: 输出文件路径
    :return: 合并是否成功
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', audio_file,
            '-i', video_file,
            '-c:v', 'copy',  # 视频流直接复制
            '-c:a', 'aac',  # 音频转AAC格式
            output_file
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.path.exists(output_file):
            os.remove(audio_file)
            os.remove(video_file)
            return True
        return False
    except subprocess.CalledProcessError as e:
        print(f"合并失败: {e.stderr.decode('utf-8')}")
        return False
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return False


def get_video(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.67',
        'Referer': url
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()  # 检查请求是否成功

    # 提取标题
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', resp.text, re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
    else:
        raise ValueError("无法提取标题")

    # 获取音频和视频
    json_data_match = re.search(r'<script>window.__playinfo__=(.*?)</script>', resp.text, re.DOTALL)
    if json_data_match:
        json_data = json.loads(json_data_match.group(1))
    else:
        raise ValueError("无法提取播放信息")

    audio_url = json_data['data']['dash']['audio'][0]['backupUrl'][0]
    video_url = json_data['data']['dash']['video'][0]['backupUrl'][0]

    # 下载音频和视频
    audio_filename = f"{title}_{int(time.time())}.mp3"
    video_filename = f"{title}_{int(time.time())}.mp4"
    with requests.get(audio_url, headers=headers, stream=True) as audio_resp, \
            requests.get(video_url, headers=headers, stream=True) as video_resp:
        audio_resp.raise_for_status()
        video_resp.raise_for_status()

        with open(audio_filename, 'wb') as audio_file, open(video_filename, 'wb') as video_file:
            for chunk in audio_resp.iter_content(chunk_size=8192):
                audio_file.write(chunk)
            for chunk in video_resp.iter_content(chunk_size=8192):
                video_file.write(chunk)

    # 合并音频和视频
    output_filename = f"{title}.mp4"
    if merge_av(audio_filename, video_filename, output_filename):
        print(f"合并成功，输出文件: {output_filename}")
    else:
        print("合并失败")


# 使用示例
if __name__ == "__main__":
    video_url = "https://www.bilibili.com/video/BV1PkTszjE11?t=1.0"
    get_video(video_url)
