import json,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor,as_completed
root=Path(__file__).resolve().parents[2]
raw=json.loads((root/'.private/course-raw.json').read_text())
base=urlsplit(raw['source']);origin=base.scheme+'://'+base.netloc
user_id='u_lp_1672668433_63b2e5116e490_Xa6MOm'

def get(index,line):
 lesson=raw['lessons'][index];v=lesson['detail']['data']['video_info']
 body={'org_app_id':v['material_app_id'],'app_id':v['app_id'],'user_id':user_id,'play_sign':[v['play_sign']],'play_line':line,'opr_sys':'MacIntel'}
 req=urllib.request.Request(origin+'/xe.material-center.play/getPlayUrl',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Referer':raw['source'],'User-Agent':'Mozilla/5.0'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=40) as r:
   c=r.read();result=json.loads(c)
  data=result.get('data',{});play=data.get(v['play_sign'],{})
  summary={'index':index,'id':lesson['id'],'line':line,'code':result.get('code'),'keys':sorted(play.get('play_list',{})),'support':play.get('support_list'),'default':play.get('default_play')}
  return {'summary':summary,'result':result}
 except Exception as e:
  return {'summary':{'index':index,'id':lesson['id'],'line':line,'error':type(e).__name__}}

results=[]
with ThreadPoolExecutor(max_workers=2) as p:
 tasks=[p.submit(get,i,line) for i in [0,20,40] for line in ['B','C']]
 for f in as_completed(tasks):
  v=f.result();results.append(v);print(json.dumps(v['summary'],ensure_ascii=False),flush=True)
p=root/'.private/quality-research/line-comparison.json';p.write_text(json.dumps(results,ensure_ascii=False,indent=2));p.chmod(0o600)
