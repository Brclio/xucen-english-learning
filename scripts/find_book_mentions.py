"""Local ASR index for reviewing book mentions; not a verified course transcript."""
import json,time,sys
from pathlib import Path
import mlx_whisper
ROOT=Path(__file__).resolve().parents[1]
MODEL='/Users/huangjiabao/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/snapshots/a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb'
course=json.loads((ROOT/'course-data.json').read_text())
english_review='--english-readaloud' in sys.argv
order=list(range(16,41)) if english_review else [8,11,12,13,14,0,1,2,3,4,5,6,7,9,10,15]+list(range(16,41))
out=ROOT/('.private/book-mention-transcripts-en' if english_review else '.private/book-mention-transcripts');out.mkdir(parents=True,exist_ok=True)
for i in order:
 l=course['lessons'][i];p=out/(l['id']+'.json')
 if p.exists():
  try:
   cached=json.loads(p.read_text())
   if cached.get('lessonId')==l['id'] and 'segments' in cached:continue
  except (ValueError,OSError):pass
 start=time.monotonic()
 try:
  result=mlx_whisper.transcribe(str(ROOT/l['audioPath']),path_or_hf_repo=MODEL,language='en' if english_review else 'zh',verbose=None,condition_on_previous_text=False,temperature=0,initial_prompt='English picture book read-aloud.' if english_review else '这是中文和英文混合的英语启蒙课程。请保留英语书名和英语原话。')
 except Exception as error:
  print(f"FAILED {l['title']} {type(error).__name__}: {error}",flush=True)
  continue
 result={k:result[k] for k in ['text','segments','language'] if k in result}
 result.update({'lessonId':l['id'],'lessonTitle':l['title'],'sourceAudio':l['audioPath'],'method':'Local MLX Whisper large-v3-turbo; machine transcript, unverified'})
 temp=p.with_suffix('.json.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(p)
 text_path=out/(l['id']+'.txt');text_path.write_text('\n'.join(f"[{s['start']:.1f}–{s['end']:.1f}] {s['text']}" for s in result['segments']));text_path.chmod(0o600)
 print(f"DONE {l['title']} {time.monotonic()-start:.1f}s",flush=True)
