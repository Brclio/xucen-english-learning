"""Losslessly split source duplicate presentation timestamps, preserving payloads."""
import hashlib,json,subprocess,sys
from pathlib import Path
from assets import probe,sha256
ROOT=Path(__file__).resolve().parents[1]

def packet_data(path,source=False):
    cmd=['ffprobe','-v','error']
    if source:cmd+=['-protocol_whitelist','file,crypto,data','-allowed_extensions','ALL']
    cmd+=['-show_packets','-show_data_hash','sha256','-show_entries','packet=stream_index,pts,dts,data_hash','-of','json',str(path)]
    return json.loads(subprocess.run(cmd,capture_output=True,text=True,check=True).stdout)['packets']

def digest(packets):
    by={}
    for p in packets:by.setdefault(p['stream_index'],[]).append(p['data_hash'])
    return {str(k):{'packets':len(v),'orderedPayloadSha256':hashlib.sha256('\n'.join(v).encode()).hexdigest()}for k,v in by.items()}

def repair(rid):
    mpath=ROOT/'metadata/videos-manifest.json';mp=json.loads(mpath.read_text());item=mp['lessons'][rid]
    dest=ROOT/item['path'];source=ROOT/'.private/video-cache'/rid/'local.m3u8';video=[p for p in packet_data(source,True)if p['stream_index']==0]
    adjustments=[]
    for i in range(1,len(video)-1):
        p,prev,nxt=video[i],video[i-1],video[i+1]
        if p['dts']==prev['dts']:
            delta=nxt['dts']-p['dts'];assert delta>1
            adjustments.append({'packet':i,'ticks':delta//2,'ptsTicks':delta//2 if any(q['pts']==p['pts'] for q in video[:i]) else 0,'originalPts':p['pts'],'originalDts':p['dts']})
    assert adjustments and len(adjustments)<5,adjustments
    terms='+'.join(str(a['ticks'])+'*eq(N\\,'+str(a['packet'])+')'for a in adjustments)
    pts_terms='+'.join(str(a['ptsTicks'])+'*eq(N\\,'+str(a['packet'])+')'for a in adjustments)
    candidate=ROOT/'.private'/(dest.stem+'-timing-repaired.mp4')
    cmd=['ffmpeg','-nostdin','-v','error','-y','-protocol_whitelist','file,crypto,data','-allowed_extensions','ALL','-i',str(source),'-map','0:v:0','-map','0:a?','-c','copy','-bsf:v','setts=pts=PTS+'+pts_terms+':dts=DTS+'+terms,'-movflags','+faststart',str(candidate)]
    r=subprocess.run(cmd,capture_output=True,text=True,check=True);assert not r.stderr,r.stderr
    before=digest(packet_data(dest));after=digest(packet_data(candidate));assert before==after
    r=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','json',str(candidate)],capture_output=True,text=True,check=True);assert not r.stderr,r.stderr
    frames=json.loads(r.stdout)['frames'];times=[float(f['best_effort_timestamp_time'])for f in frames];assert all(b>a for a,b in zip(times,times[1:]))
    r=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(candidate),'-fps_mode','passthrough','-enc_time_base:v','1:90000','-f','null','-'],capture_output=True,text=True,check=True);assert not r.stderr,r.stderr
    info=probe(candidate);assert abs(info['duration']-item['media']['duration'])<.01
    proof={'courseResourceId':rid,'reason':'Source supplies distinct adjacent video packets with identical DTS. Both are retained; split the original decode interval equally; adjust PTS only if also duplicated.','packetAdjustments':adjustments,'timebase':'1/90000','videoFrames':len(frames),'nonmonotonicDecodedFramesAfter':0,'streamPayloadsUnchanged':True,'streamDigests':after,'reencoded':False,'durationUnchanged':True,'validation':'Full video/audio decode with passthrough and output timebase 1/90000: zero errors'}
    report=ROOT/'metadata'/(dest.stem[:2]+'-timing-repair.json');report.write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    dest.replace(ROOT/'.private'/(dest.stem+'-original-timestamps.mp4'));candidate.replace(dest)
    item.update(bytes=dest.stat().st_size,sha256=sha256(dest),media=info,timingRepair=proof);mpath.write_text(json.dumps(mp,ensure_ascii=False,indent=2))
    vpath=ROOT/'metadata/video-validation.json';v=json.loads(vpath.read_text());v['lessons'][rid].update(valid=True,fullDecode=True,error='',sourceTimingWarnings='Source duplicate PTS/DTS corrected losslessly; all compressed video/audio payload hashes unchanged.',validationTimingNormalization=False,timingRepairApplied=True,validationOutputTimeBase='1/90000',frames=len(frames));vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2))
    print(json.dumps(proof,ensure_ascii=False),flush=True)
if __name__=='__main__':repair(sys.argv[1])
