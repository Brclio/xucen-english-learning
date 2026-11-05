"""Read the course browser session without exporting credentials into the archive."""
import json, os, subprocess
from pathlib import Path
SESSION = os.environ.get('COURSE_BROWSER_SESSION', 'xucen-course')

def browser(*args, timeout=90):
    p = subprocess.run(['agent-browser','--session',SESSION,'--json',*args],capture_output=True,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError(p.stderr[:250] or 'Browser command failed')
    x=json.loads(p.stdout)
    if not x.get('success'): raise RuntimeError('Browser operation failed')
    return x.get('data',{})

def evaluate(js):
    import base64
    result=browser('eval','-b',base64.b64encode(js.encode()).decode())
    return result.get('result',result)

def requests():
    return browser('network','requests','--type','xhr,fetch')['requests']

def save_response(request, dest):
    data=browser('network','request',request['requestId'])
    dest=Path(dest)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    dest.chmod(0o600)
    return data

if __name__=='__main__':
    print(json.dumps({'url':evaluate('location.href'), 'requests':[{'id':r['requestId'],'method':r['method'],'url':r['url'].split('?')[0]} for r in requests() if 'aegis' not in r['url'] and 'sensors' not in r['url']]},ensure_ascii=False,indent=2))
