from flask import Flask, render_template, request, jsonify
import yt_dlp
import whisper
import requests
import os
import threading
import uuid

app = Flask(__name__)

def download_bilibili(url, filename):
    """下载B站视频音频"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'/tmp/temp_{filename}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)
    return f'/tmp/temp_{filename}.mp3'

def get_text_summary(text):
    """获取文本总结（同时返回思维导图和文章格式）"""
    api_url = 'https://xiaoai.plus/v1/chat/completions'
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-j29yjWFosoZKE247028dD1F7961c49F59b78E6767b889d58"
    }
    
    # 生成思维导图格式
    mindmap_data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": """请将内容总结成markdown格式的大纲，使用#、##、###等标记层级，例如：
# 主要内容
## 核心观点1
### 细节1
### 细节2
## 核心观点2
### 要点1
### 要点2"""},
            {"role": "user", "content": text}
        ]
    }
    mindmap_response = requests.post(api_url, headers=headers, json=mindmap_data)
    mindmap = mindmap_response.json()['choices'][0]['message']['content']
    
    # 生成文章格式
    article_data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "请将内容改写成小红书风格的文章，使用表情符号和简单的语言："},
            {"role": "user", "content": text}
        ]
    }
    article_response = requests.post(api_url, headers=headers, json=article_data)
    article = article_response.json()['choices'][0]['message']['content']
    
    return {
        "mindmap": mindmap,
        "article": article
    }

# 存储任务状态
tasks = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    urls = request.json.get('urls', [])
    if not urls:
        return jsonify({"error": "请提供至少一个URL"}), 400
    
    task_ids = []
    for url in urls:
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        
        def process_video(url=url, task_id=task_id):
            try:
                # 1. 下载音频
                tasks[task_id] = {"status": "下载中...", "url": url}
                audio_file = download_bilibili(url, task_id)
                
                # 2. 转文字
                tasks[task_id]["status"] = "转换文字中..."
                model = whisper.load_model("tiny")
                result = model.transcribe(audio_file)
                
                # 3. 获取总结
                tasks[task_id]["status"] = "生成总结中..."
                summary = get_text_summary(result["text"])
                
                tasks[task_id] = {
                    "status": "完成",
                    "url": url,
                    "result": summary["article"],
                    "mindmap": summary["mindmap"]
                }
                
            except Exception as e:
                tasks[task_id] = {
                    "status": "失败",
                    "url": url,
                    "result": str(e)
                }
            finally:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
        
        thread = threading.Thread(target=process_video)
        thread.start()
    
    return jsonify({"task_ids": task_ids})

@app.route('/status/<task_id>')
def status(task_id):
    if task_id in tasks:
        return jsonify({"data": tasks[task_id]})
    return jsonify({"error": "任务不存在"})

if __name__ == '__main__':
    app.run(debug=True, port=8080)