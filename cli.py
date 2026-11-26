import argparse
import json
from pathlib import Path
from threadstudio.source import fetch_thread, save_project
from threadstudio.render import render

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Threads Studio renderer')
    p.add_argument('--url');p.add_argument('--project');p.add_argument('--output',required=True)
    p.add_argument('--style',choices=['center','top','grid'],default='center')
    p.add_argument('--background',default='');p.add_argument('--music',default='')
    p.add_argument('--voice',default='ms-MY-YasminNeural');p.add_argument('--no-speech',action='store_true')
    p.add_argument('--max-posts',type=int,default=12);p.add_argument('--resolution',type=int,choices=[720,1080],default=720)
    a=p.parse_args()
    if not a.url and not a.project:p.error('Cần --url hoặc --project')
    d=fetch_thread(a.url) if a.url else json.loads(Path(a.project).read_text(encoding='utf8'))
    render(d,a.output,style=a.style,background=a.background,music=a.music,voice=a.voice,speech=not a.no_speech,max_posts=a.max_posts,resolution=a.resolution)
