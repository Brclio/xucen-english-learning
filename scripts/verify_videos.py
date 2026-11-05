"""Decode every archived video end-to-end and check duration/quality/hashes."""
import concurrent.futures as cf
import json,subprocess,time
from pathlib import Path
from assets import probe,sha256
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'metadata/videos-manifest.json'
RESULT=ROOT/'metadata/video-validation.json'

def check(rid,item):
    p=ROOT/item['path'];data=probe(p)
    r=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(p),'-fps_mode','passthrough','-enc_time_base:v','1:90000','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=600)
    errors=r.stderr.strip()
    timing_warnings=''
    if errors and all('Application provided invalid, non monotonically increasing dts to muxer' in line for line in errors.splitlines()):
        timing_warnings=errors
        r=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(p),'-vf','setpts=N/(25*TB)','-af','asetpts=N/SR/TB','-fps_mode','passthrough','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=600)
        errors=r.stderr.strip()
    actual_hash=sha256(p)
    valid=r.returncode==0 and not errors and abs(data['duration']-item['expectedDuration'])<=2 and data['height']>=720 and actual_hash==item['sha256']
    print(('VERIFIED 'if valid else'FAILED ')+p.name,flush=True)
    return rid,{'path':item['path'],'sha256':actual_hash,'valid':valid,'fullDecode':r.returncode==0 and not errors,'duration':data['duration'],'width':data['width'],'height':data['height'],'error':errors[:1500],'sourceTimingWarnings':timing_warnings[:1500],'validationTimingNormalization':bool(timing_warnings)}

def main():
    results=json.loads(RESULT.read_text())if RESULT.exists()else{'lessons':{}}
    pending={}
    initial=json.loads(MANIFEST.read_text())if MANIFEST.exists()else{'lessons':{}}
    seen={rid for rid,item in results['lessons'].items() if item['valid'] and rid in initial['lessons'] and item.get('sha256')==initial['lessons'][rid]['sha256'] and (ROOT/item['path']).exists() and sha256(ROOT/item['path'])==item.get('sha256')}
    with cf.ThreadPoolExecutor(max_workers=2)as pool:
        while len(seen)<41 or pending:
            data=json.loads(MANIFEST.read_text())if MANIFEST.exists()else{'lessons':{}}
            for rid,item in data['lessons'].items():
                if rid not in seen:
                    seen.add(rid);pending[pool.submit(check,rid,item)]=rid
            for future in list(pending):
                if future.done():
                    rid,item=future.result();results['lessons'][rid]=item;del pending[future]
                    tmp=RESULT.with_suffix('.tmp');tmp.write_text(json.dumps(results,ensure_ascii=False,indent=2));tmp.replace(RESULT)
            if len(seen)>=41 and not pending:break
            time.sleep(5)
    print('Full video decode validation complete',flush=True)
if __name__=='__main__':main()
