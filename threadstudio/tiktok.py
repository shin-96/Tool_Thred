"""Official Content Posting API. Browser-assisted upload lives in browser_publish.py."""
from pathlib import Path
from urllib.parse import urlsplit
import requests

from .render import probe


class TikTokError(RuntimeError):
    def __init__(self,message,uncertain=False):super().__init__(message);self.uncertain=uncertain


def chunk_plan(size):
    if size<=0 or size>4*1024**3:raise ValueError('Video phải có dữ liệu và nhỏ hơn hoặc bằng 4 GB.')
    nominal=10*1024**2
    count=max(1,size//nominal)
    # TikTok combines the remainder with the final chunk (which may be larger).
    return nominal if count>1 else size,count


class TikTokAPI:
    BASE='https://open.tiktokapis.com'
    def __init__(self,token,session=None):
        if not token.strip():raise ValueError('Chưa nhập access token TikTok.')
        self.token=token.strip();self.session=session or requests.Session()

    def _post(self,path,payload):
        try:
            r=self.session.post(self.BASE+path,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json; charset=UTF-8'},json=payload,timeout=35,allow_redirects=False)
            data=r.json()
        except requests.RequestException as e:raise TikTokError('Kết nối TikTok thất bại; chưa xác nhận kết quả. Tra cứu lịch sử trước khi gửi lại.',True) from e
        except ValueError as e:raise TikTokError('TikTok trả phản hồi không hợp lệ; chưa xác nhận kết quả.',True) from e
        error=data.get('error',{})
        if not r.ok or error.get('code')!='ok':
            code=error.get('code',str(r.status_code))
            # Never echo a response body or upload URL that could contain a credential.
            hints={'access_token_invalid':'Token hết hạn hoặc không hợp lệ. Kết nối lại tài khoản.','scope_not_authorized':'Token chưa có quyền video.upload / video.publish tương ứng.','unaudited_client_can_only_post_to_private_accounts':'Ứng dụng TikTok chưa được duyệt cho hình thức đăng này.','spam_risk_too_many_pending_share':'TikTok đã đạt giới hạn video chờ hoàn tất.','rate_limit_exceeded':'TikTok giới hạn tần suất; chờ rồi kiểm tra trạng thái.'}
            raise TikTokError(hints.get(code,'TikTok từ chối yêu cầu: '+code))
        return data.get('data',{})

    def creator(self):return self._post('/v2/post/publish/creator_info/query/',{})
    def status(self,publish_id):return self._post('/v2/post/publish/status/fetch/',{'publish_id':publish_id})

    def upload(self,path,caption,mode='inbox',privacy=None,creator=None,on_init=lambda _:None,progress=lambda _:None,post_options=None):
        path=Path(path).resolve()
        if not path.is_file():raise ValueError('Không tìm thấy video.')
        mime={'.mp4':'video/mp4','.mov':'video/quicktime','.webm':'video/webm'}.get(path.suffix.lower())
        if not mime:raise ValueError('TikTok API nhận MP4, MOV hoặc WebM. Hãy xuất MP4 trước.')
        if len(caption.encode('utf-16-le'))//2>2200:raise ValueError('Caption TikTok tối đa 2200 ký tự UTF-16.')
        if mode not in {'inbox','direct'}:raise ValueError('Hình thức TikTok không hợp lệ.')
        info=probe(path);video=next((s for s in info['streams'] if s['codec_type']=='video'),None)
        if not video:raise ValueError('Tệp không có luồng video.')
        if not 360<=video['width']<=4096 or not 360<=video['height']<=4096:raise ValueError('TikTok yêu cầu chiều rộng và cao từ 360 đến 4096 pixel.')
        duration=float(info['format']['duration'])
        if mode=='inbox' and duration>600:raise ValueError('Gửi vào hộp thư hỗ trợ video tối đa 10 phút.')
        chunk,count=chunk_plan(path.stat().st_size)
        payload={'source_info':{'source':'FILE_UPLOAD','video_size':path.stat().st_size,'chunk_size':chunk,'total_chunk_count':count}}
        if mode=='direct':
            if creator is None:creator=self.creator()
            if not privacy or privacy not in creator.get('privacy_level_options',[]):raise ValueError('Chọn quyền xem trong các lựa chọn do TikTok trả về.')
            if duration>creator.get('max_video_post_duration_sec',0):raise ValueError('Video dài hơn giới hạn đăng của tài khoản TikTok.')
            options=post_options or {}
            payload['post_info']={'title':caption,'privacy_level':privacy,'disable_comment':bool(creator.get('comment_disabled')) or not options.get('allow_comment',False),'disable_duet':bool(creator.get('duet_disabled')) or not options.get('allow_duet',False),'disable_stitch':bool(creator.get('stitch_disabled')) or not options.get('allow_stitch',False),'brand_content_toggle':bool(options.get('branded',False)),'brand_organic_toggle':bool(options.get('own_brand',False)),'is_aigc':bool(options.get('aigc',False))}
        endpoint='/v2/post/publish/video/init/' if mode=='direct' else '/v2/post/publish/inbox/video/init/'
        result=self._post(endpoint,payload);publish_id=result['publish_id'];on_init(publish_id)
        upload_url=result['upload_url'];u=urlsplit(upload_url)
        if u.scheme!='https' or not (u.hostname or '').endswith('.tiktokapis.com'):raise TikTokError('Địa chỉ tải lên do TikTok trả về không hợp lệ.')
        total=path.stat().st_size
        with path.open('rb') as f:
            for i in range(count):
                start=f.tell();block=f.read(chunk if i<count-1 else total-start);end=start+len(block)-1
                try:
                    r=self.session.put(upload_url,data=block,headers={'Content-Type':mime,'Content-Length':str(len(block)),'Content-Range':f'bytes {start}-{end}/{total}'},timeout=180,allow_redirects=False)
                except requests.RequestException as e:raise TikTokError('Tải video bị gián đoạn. Đã lưu publish_id; tra cứu trạng thái trước khi gửi lại.') from e
                if r.status_code != (201 if i==count-1 else 206):raise TikTokError('TikTok chưa xác nhận phần video vừa gửi. Kiểm tra trạng thái trong lịch sử.',True)
                progress((end+1)/total)
        return publish_id
