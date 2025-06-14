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
            'ffmpeg.exe',
            '-i', audio_file,
            '-i', video_file,
            '-c:v', 'copy',  # 视频流直接复制
            '-c:a', 'aac',  # 音频转AAC格式
            output_file
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.path.exists(output_file):
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

    # 创建下载目录
    download_dir = os.path.join(os.getcwd(), 'downloads')
    os.makedirs(download_dir, exist_ok=True)

    # 获取页面
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()

    # 提取标题
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', resp.text, re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
    else:
        raise ValueError("无法提取标题")

    # 生成输出文件路径（这里不加时间戳）
    output_path = os.path.join(download_dir, f"{title}.mp4")

    # 如果目标文件已存在，直接返回标题，跳过下载
    if os.path.exists(output_path):
        print(f"文件已存在，跳过下载：{output_path}")
        return title

    # 提取播放信息 JSON
    json_data_match = re.search(r'<script>window.__playinfo__=(.*?)</script>', resp.text, re.DOTALL)
    if json_data_match:
        json_data = json.loads(json_data_match.group(1))
    else:
        raise ValueError("无法提取播放信息")

    # 提取音视频 URL
    audio_url = json_data['data']['dash']['audio'][0]['backupUrl'][0]
    video_url = json_data['data']['dash']['video'][0]['backupUrl'][0]

    # 生成带时间戳的临时保存路径，防止文件覆盖
    timestamp = int(time.time())
    audio_path = os.path.join(download_dir, f"{title}_{timestamp}.mp3")
    video_path = os.path.join(download_dir, f"{title}_{timestamp}.mp4")

    # 下载音频和视频
    with requests.get(audio_url, headers=headers, stream=True) as audio_resp, \
            requests.get(video_url, headers=headers, stream=True) as video_resp:
        audio_resp.raise_for_status()
        video_resp.raise_for_status()

        with open(audio_path, 'wb') as audio_file, open(video_path, 'wb') as video_file:
            for chunk in audio_resp.iter_content(chunk_size=8192):
                audio_file.write(chunk)
            for chunk in video_resp.iter_content(chunk_size=8192):
                video_file.write(chunk)

    # 合并音视频
    if merge_av(audio_path, video_path, output_path):
        print(f"合并成功，输出文件: {output_path}")
        # 下载完成后删除临时文件
        os.remove(audio_path)
        os.remove(video_path)
    else:
        print("合并失败")

    return title


# 使用示例
if __name__ == "__main__":
    video_url = "https://www.bilibili.com/video/BV1PkTszjE11?t=1.0"
    get_video(video_url)
