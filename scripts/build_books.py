"""Merge verified course book references into an offline shelf and Markdown index."""
import json,copy
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
def read(path,default):
 p=ROOT/path
 return json.loads(p.read_text()) if p.exists() else default
base=read('metadata/book-catalog-source.json',{'books':[]})
extra=read('metadata/book-additional-mentions.json',{})
course=read('course-data.json',{'lessons':[]})
lessons={x['id']:x for x in course['lessons']}
books=[];seen={}
for item in base['books']+extra.get('books',[]):
 b=copy.deepcopy(item);b.setdefault('kind','book')
 if b['kind']=='picture-book':b['kind']='book'
 for e in b.get('mentionEvidence',[]):
  e['kind']={'spoken-title':'spoken','visible-cover':'visual'}.get(e.get('kind'),e.get('kind'))
 key=b.get('isbn') or b.get('id') or b['title'].casefold()
 if key in seen:
  existing=seen[key]
  existing['lessonIds']=list(dict.fromkeys(existing.get('lessonIds',[])+b.get('lessonIds',[])))
  existing['mentionEvidence']=existing.get('mentionEvidence',[])+b.get('mentionEvidence',[])
  continue
 if b.get('cover') and not (ROOT/b['cover']).is_file():raise ValueError('Cover missing: '+b['cover'])
 for e in b.get('mentionEvidence',[]):
  if e['lessonId'] not in lessons:raise ValueError('Unknown lesson: '+e['lessonId'])
 seen[key]=b;books.append(b)
coverage=extra.get('reviewCoverage',{})
scope=extra.get('scopeNote') or '已核实课名明确对应的25本小猪小象绘本；正在复核全课程中的其他口头提及书目。封面全部保存在本地，点击关联课时可回到课程。'
result={'title':'课程绘本书架','updatedAt':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),'books':books,'scopeNote':scope,'reviewCoverage':coverage,'seriesMentions':extra.get('seriesMentions',[]),'uncertainMentions':extra.get('uncertainMentions',[]),'otherReferences':extra.get('otherReferences',extra.get('otherReadingMentions',[]))}
(ROOT/'books-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(ROOT/'books-data.js').write_text('window.BOOKS_DATA = '+json.dumps(result,ensure_ascii=False,indent=2).replace('</','<\\/')+';\n')
lines=['# 课程绘本书架','',scope,'',f'共 {len(books)} 项已核实书目（单本和系列分别标注）。','', '[打开绘本网页](books.html)','']
for b in books:
 lines += ['## '+b['title'],'',f"- 类型：{'系列' if b['kind']=='series' else '单本'}",f"- 作者：{b.get('author','待核实')}"]
 if b.get('isbn'):lines.append('- ISBN：'+b['isbn'])
 if b.get('sourceUrl'):lines.append('- 出版信息：[来源]('+b['sourceUrl']+')')
 if b.get('note'):lines += ['',b['note']]
 if b.get('editionNote') and b.get('editionNote')!=b.get('note'):lines += ['',b['editionNote']]
 if b.get('cover'):lines += ['',f"![{b['title']}]({quote(b['cover'],safe='/')})"]
 for e in b.get('mentionEvidence',[]):
  l=lessons[e['lessonId']];suffix='&t='+str(e['time']) if e.get('time') is not None else ''
  time=f" · {int(e['time'])//60}:{int(e['time'])%60:02d}" if isinstance(e.get('time'),(int,float)) else ''
  lines.append(f"- 提及位置：[{l['title']}{time}](index.html#lesson={quote(l['id'])}{suffix})")
  if e.get('note'):lines.append('  '+e['note'])
 lines.append('')
for key,heading in [('seriesMentions','课程提及的系列'),('uncertainMentions','尚未确定具体版本的提及'),('otherReferences','课程其他阅读参考')]:
 if result[key]:
  lines += ['## '+heading,'']
  for u in result[key]:
   lines += ['### '+str(u.get('title') or u.get('text') or u.get('name') or u),'']
   if u.get('note'):lines += [u['note'],'']
   if u.get('sourceUrl'):lines += ['[书目信息来源]('+u['sourceUrl']+')','']
   for e in u.get('mentionEvidence',[]):
    if e.get('lessonId') not in lessons:continue
    l=lessons[e['lessonId']];suffix='&t='+str(e['time']) if e.get('time') is not None else ''
    lines.append(f"- 提及位置：[{l['title']}](index.html#lesson={quote(l['id'])}{suffix})")
   lines.append('')
(ROOT/'绘本书目.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'books':len(books),'covers':sum(bool(b.get('cover')) for b in books),'coverage':coverage},ensure_ascii=False))
