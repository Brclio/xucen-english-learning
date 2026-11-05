"""Decode the provider's ordinary URL transport encoding, preserving offered qualities."""
import base64, json, os
from pathlib import Path

def decode_video_urls(value):
    if isinstance(value,list):return value
    if value.endswith('__ba'):
        value=base64.b64decode(value[:-4].translate(str.maketrans('@#$%','1234'))).decode()
    result=json.loads(value)
    if not isinstance(result,list):raise ValueError('Expected video variants')
    return result

def export_variants(raw='.private/course-raw.json', dest='.private/video-variants.json'):
    data=json.loads(Path(raw).read_text())
    result={'lessons':{}}
    titles={x['resource_id']:x['resource_title'] for x in data['list']}
    for lesson in data['lessons']:
        info=lesson['detail']['data']
        result['lessons'][lesson['id']]={'title':titles[lesson['id']],'duration':info['video_info']['video_length'],'variants':decode_video_urls(info['video_urls'])}
    Path(dest).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    os.chmod(dest,0o600)
    return result

if __name__=='__main__':
    x=export_variants()
    from collections import Counter
    print(json.dumps({'lessons':len(x['lessons']),'qualitySets':dict(Counter(','.join(v.get('definition_p','')for v in l['variants'])for l in x['lessons'].values()))},ensure_ascii=False))
