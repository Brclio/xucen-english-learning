"""Archive the account-authorized HLS videos with their supplied AES-128 keys.

Uses only exposed playback variants and the key URI in each authorized playlist.
Keeps encrypted segment caches and short-lived playback URLs under .private.
"""
from __future__ import annotations
import concurrent.futures as cf
import hashlib,json,os,re,subprocess,threading,time
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import requests
from assets import probe,sha256,choose_highest
from video_format import export_variants

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
PRIVATE=ROOT/'.private/video-cache';PRIVATE.mkdir(parents=True,exist_ok=True);PRIVATE.chmod(0o700)
MANIFEST=ROOT/'metadata/videos-manifest.json'
SOURCE='https://appuzenkpej8854.h5.xet.pomoho.com/p/course/column/p_673aa9b1e4b023c058a64b53'
lock=threading.Lock();tls=threading.local()

def session():
    if not hasattr(tls,'session'):
        tls.session=requests.Session();tls.session.headers.update({'User-Agent':'Mozilla/5.0','Referer':SOURCE})
    return tls.session

def fetch(url,path=None,minimum=1):
    if path and path.exists() and path.stat().st_size>=minimum:return path.read_bytes()
    for attempt in range(6):
        try:
            r=session().get(url,timeout=(15,50));r.raise_for_status();data=r.content
            if len(data)<minimum:raise ValueError('Incomplete resource')
            if path:
                temp=path.with_suffix(path.suffix+'.part');temp.write_bytes(data);temp.chmod(0o600);temp.replace(path)
            return data
        except (requests.RequestException,ValueError):
            if attempt==5:raise RuntimeError('Resource transfer failed after retries') from None
            time.sleep(min(2**attempt,8))

def save(state):
    tmp=MANIFEST.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2));tmp.replace(MANIFEST)

def path_title(title):return re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',title)

def process(rid,lesson,pool,state):
    title=lesson['title'];variants=lesson['variants']
    candidates=[dict(v,quality=v.get('definition_p',v.get('definition','')),url=v.get('url',v.get('play_url','')))for v in variants]
    selected=choose_highest(candidates);variant=selected['variant'];url=variant['url']
    dest=Path('media/videos')/(path_title(title)+'.mp4');dest.parent.mkdir(parents=True,exist_ok=True)
    expected=float(lesson['duration']);cache=PRIVATE/rid;cache.mkdir(exist_ok=True)
    before=None
    if dest.exists():
        try:
            before=probe(dest)
            if abs(before['duration']-expected)>2:before=None
        except Exception:pass
    if before is None:
        text=fetch(url).decode('utf-8-sig')
        if '#EXT-X-ENDLIST' not in text:raise RuntimeError('Expected a complete VOD playlist')
        if '#EXT-X-STREAM-INF' in text:raise RuntimeError('Master playlist needs exposed variant selection')
        original=cache/'original.m3u8';original.write_text(text);original.chmod(0o600)
        durations=[float(x)for x in re.findall(r'#EXTINF:([\d.]+)',text)]
        if abs(sum(durations)-expected)>2:raise RuntimeError('Playlist duration does not match course duration')
        lines=[];segments=[];key_urls={}
        for line in text.splitlines():
            if line.startswith('#EXT-X-KEY:'):
                method=re.search(r'METHOD=([^,]+)',line)[1]
                if method not in ('NONE','AES-128'):raise RuntimeError('Unsupported encryption method; no alternative attempted')
                m=re.search(r'URI="([^"]+)"',line)
                if m:
                    key_url=urljoin(url,m[1]);key_name='key-'+hashlib.sha256(key_url.encode()).hexdigest()[:12]+'.bin'
                    key=fetch(key_url,cache/key_name,16)
                    if len(key)!=16:raise RuntimeError('Authorized key response is not AES-128')
                    line=line.replace(m[1],key_name);key_urls[key_name]=key_url
            elif line and not line.startswith('#'):
                name=f'segment-{len(segments):05d}.ts';segments.append((urljoin(url,line),cache/name));line=name
            lines.append(line)
        playlist=cache/'local.m3u8';playlist.write_text('\n'.join(lines)+'\n');playlist.chmod(0o600)
        futures=[pool.submit(fetch,u,p,16)for u,p in segments]
        completed=0;last=time.monotonic()
        for future in cf.as_completed(futures):
            future.result();completed+=1
            if time.monotonic()-last>20:
                print(f'{title}: {completed}/{len(segments)} segments',flush=True);last=time.monotonic()
        part=dest.with_suffix('.part.mp4');log=cache/'ffmpeg.log'
        # The archived source for this lesson has two distinct IDR packets at the
        # same PTS/DTS. A verified timestamp-only 20 ms split retains every
        # video/audio payload. See metadata/05-timing-repair.json.
        timing_filter=[]
        if rid=='v_674d33cee4b0694c950b2c81' and expected==674:
            timing_filter=['-bsf:v','setts=pts=PTS+1800*eq(N\\,9026):dts=DTS+1800*eq(N\\,9026)']
        elif rid=='v_67568bf8e4b023c058b2f644' and expected==1029:
            timing_filter=['-bsf:v','setts=pts=PTS+1800*eq(N\\,15056):dts=DTS+1800*eq(N\\,15056)']
        with log.open('w')as err:
            result=subprocess.run(['ffmpeg','-hide_banner','-loglevel','warning','-y','-protocol_whitelist','file,crypto,data','-allowed_extensions','ALL','-i',str(playlist),'-map','0:v:0','-map','0:a?','-c','copy',*timing_filter,'-movflags','+faststart',str(part)],stdout=subprocess.DEVNULL,stderr=err)
        if result.returncode:raise RuntimeError('Lossless video remux failed')
        before=probe(part)
        if abs(before['duration']-sum(durations))>2:raise RuntimeError('Downloaded video duration mismatch')
        expected_height=int(re.search(r'\d+',variant.get('definition_p','0'))[0])
        if expected_height and before['height']<expected_height:raise RuntimeError('Resolution lower than selected variant')
        part.replace(dest)
    record={'path':str(dest),'bytes':dest.stat().st_size,'sha256':sha256(dest),'media':before,'quality':f"{before['height']}p",'qualityLabel':variant.get('definition_name',variant.get('desc','')),'exposedQualities':[v.get('definition_p',v.get('definition',''))for v in variants],'selectionReason':selected['reason'],'expectedDuration':expected,'sourceUrl':url.split('?')[0],'videoStatus':'downloaded','status':'downloaded','qualityVerification':'All 41 actual getPlayUrl A-line responses expose only 720p_hls and mp3; matches course video_urls.','encryption':'AES-128 HLS, authorized playlist key, lossless remux'}
    with lock:
        state['lessons'][rid]=record;state['errors']=[e for e in state['errors']if e['id']!=rid];save(state)
    print(f"DONE {title}: {before['width']}x{before['height']}, {dest.stat().st_size/1024/1024:.1f} MiB",flush=True)
    return record

def main():
    variants=export_variants()
    state=json.loads(MANIFEST.read_text())if MANIFEST.exists()else{'lessons':{},'errors':[]}
    with cf.ThreadPoolExecutor(max_workers=int(os.environ.get('VIDEO_SEGMENT_WORKERS','24')))as segments,cf.ThreadPoolExecutor(max_workers=2)as lessons:
        fut={lessons.submit(process,rid,lesson,segments,state):(rid,lesson)for rid,lesson in variants['lessons'].items()}
        for future in cf.as_completed(fut):
            rid,lesson=fut[future]
            try:future.result()
            except Exception as exc:
                with lock:
                    state['errors']=[e for e in state['errors']if e['id']!=rid]+[{'id':rid,'title':lesson['title'],'error':str(exc)}];save(state)
                print('FAILED '+lesson['title']+': '+str(exc),flush=True)
    print(json.dumps({'completed':len(state['lessons']),'errors':len(state['errors']),'bytes':sum(x['bytes']for x in state['lessons'].values())}),flush=True)

if __name__=='__main__':main()
