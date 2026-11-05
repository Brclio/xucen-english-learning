#!/usr/bin/env python3
"""Archive covers of additionally identified books; preserve course evidence."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import unescape
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo
from assets import download

ROOT = Path(__file__).resolve().parent.parent
LESSONS = json.loads((ROOT / 'course-data.json').read_text())['lessons']
RESEARCH = ROOT / '.private/book-research'

def evidence(n, start, end=None, kind='spoken-title', note=''):
    kind={'spoken-title':'spoken','visible-cover':'visual','read-aloud':'spoken'}.get(kind,kind)
    return {'lessonId': LESSONS[n]['id'], 'lessonTitle': LESSONS[n]['title'], 'time': start,
            'endTime': end if end is not None else start, 'kind': kind, 'note': note}

def og(name):
    body = (RESEARCH / (name + '.html')).read_text()
    if 'penguinrandomhouse.com/cover/' in body:
        return unescape(re.search(r'<img[^>]+src="(https://images\d*\.penguinrandomhouse.com/cover/[^"?]+)"', body).group(1))
    tag = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*>', body).group()
    return unescape(re.search(r'content=["\']([^"\']+)', tag).group(1))

def base(slug, title, author, source, cover, isbn, ev, **extra):
    return dict(id=slug, title=title, author=author, illustrator=author, sourceUrl=source,
                coverSourceUrl=cover, isbn=isbn, lessonIds=list(dict.fromkeys(e['lessonId'] for e in ev)),
                mentionEvidence=ev, kind='book', series='',
                editionNote='封面来自下列官方书目。课程实物的印次/ISBN未必与封面来源版本相同。', **extra)

def records():
    result = []
    author_url = 'https://www.anthonybrownebooks.com/books'
    author_html = (RESEARCH / 'anthony-browne.html').read_text()
    browne = [
        ('a-walk-in-the-park', 'A Walk in the Park', 'A WALK IN THE PARK', 148, 'spoken-title'),
        ('changes', 'Changes', 'CHANGES', 150, 'spoken-title'),
        ('willys-pictures', "Willy’s Pictures", 'WILLY’S PICTURES', 152, 'spoken-title'),
        ('my-mum', 'My Mum', 'MY MUM', 164, 'spoken-title'),
        ('my-brother', 'My Brother', 'MY BROTHER', 172, 'spoken-title'),
        ('zoo', 'Zoo', 'ZOO', 144, 'visible-cover'),
        ('little-beauty', 'Little Beauty', 'LITTLE BEAUTY', 146, 'visible-cover'),
        ('my-dad', 'My Dad', 'MY DAD', 160, 'visible-cover'),
    ]
    figures = re.findall(r'<figure\b.*?</figure>', author_html, re.S)
    for slug, title, key, t, kind in browne:
        fig = next(f for f in figures if unescape(re.sub('<[^>]+>', ' ', f)).strip().startswith(key))
        cover = unescape(re.search(r'data-image="([^"]+)"', fig).group(1))
        result.append(base('browne-' + slug, title, 'Anthony Browne', author_url, cover, None,
                           [evidence(12, t, kind=kind, note='讲师主动展示；画面与作者官网作品封面对照。')]))
    prh = [
        ('put-me-in-the-zoo', 'Put Me in the Zoo', 'Robert Lopshire', '103589/put-me-in-the-zoo-by-robert-lopshire/', '9780394800172', [evidence(7,110,141,'read-aloud','阅读片段'),evidence(8,289,317,'read-aloud','斑点动物内页与朗读内容对应')]),
        ('a-fly-went-by', 'A Fly Went By', 'Mike McClintock', '110655/a-fly-went-by-by-mike-mcclintock/', '9780394800035', [evidence(7,144,165,'read-aloud','动物追逐故事阅读片段')]),
        ('big-purple-book', 'The Big Purple Book of Beginner Books', 'P. D. Eastman; Peter Eastman; Helen Palmer; Michael Frith', '217813/the-big-purple-book-of-beginner-books-by-pd-eastman/9780307975874/', '9780307975874', [evidence(12,511,521,'spoken-title','紫色合订本封面可见；不把目录中的各篇自动视作分别提及')]),
        ('very-hungry-caterpillar', 'The Very Hungry Caterpillar', 'Eric Carle', '301943/the-very-hungry-caterpillar-by-eric-carle/', '9780399208539', [evidence(12,869,873,'spoken-title','讲师口述 Hungry Caterpillar；以作者出版社规范全名')]),
    ]
    for slug,title,author,path,isbn,ev in prh:
        b = base(slug,title,author,'https://www.penguinrandomhouse.com/books/'+path,og(slug),isbn,ev)
        if slug=='a-fly-went-by': b['illustrator']='Fritz Siebel'
        if slug=='big-purple-book': b['bookType']='picture-book-anthology'
        result.append(b)
    spots = [
        ('spot-goes-to-school','Spot Goes to School','37645/spot-goes-to-school-by-eric-hill/9780141343785','9780141343785',[evidence(12,106,110),evidence(13,613,659,'read-aloud'),evidence(4,498,542,'read-aloud')]),
        ('spot-goes-to-the-farm','Spot Goes to the Farm','37911/spot-goes-to-the-farm-by-eric-hill/9780141340845','9780141340845',[evidence(3,459,500,'visible-cover','封面部分字样、人物图案及朗读内页综合核验')]),
        ('spot-stays-overnight','Spot Stays Overnight','122787/spot-stays-overnight-by-hill-eric/9780241712351','9780241712351',[evidence(4,466,488,'visible-cover','474秒紫色正封书名可读')]),
    ]
    for slug,title,path,isbn,ev in spots:
        b=base(slug,title,'Eric Hill','https://www.penguin.co.uk/books/'+path,og(slug),isbn,ev)
        b['series']='Spot'
        if slug=='spot-stays-overnight': b['editionNote']='课程为紫色封面旧版；此处为出版社现行2025纸板版封面，同一作品，非声称课程相同印次。'
        result.append(b)
    b=base('spot-goes-on-holiday','Spot Goes on Holiday','Eric Hill',
        'https://www.penguin.co.uk/books/37693/spot-goes-on-holiday-by-eric-hill/9780141343778',
        'https://cdn.penguin.co.uk/dam-assets/books/9780141343778/9780141343778-jacket-large.jpg',
        '9780141343778',[evidence(13,500,549,'read-aloud','连续内页与朗读出现乘船、落水、毛巾、新朋友；和出版社故事介绍匹配。')])
    b['series']='Spot'; b['additionalSourceUrl']='https://shop.scholastic.co.uk/products/Spot-Goes-on-Holiday-Eric-Hill-9780140506990'
    b['editionNote']='按连续内页、朗读及出版社介绍确认作品；课程未露封面，具体版本/ISBN未确认。这里展示查得的出版版本封面。'
    result.append(b)
    result.append(base('maisy-goes-to-bed','Maisy Goes to Bed','Lucy Cousins',
        'https://www.walker.co.uk/9781406371529/maisy-goes-to-bed/',
        'https://walker-books-uk.imgix.net/covers/9781406371529.jpg?auto=format&placeholder=1',
        '9781406371529',[evidence(12,896,940,'visible-cover','正封可读标题、Lucy Cousins及A pull-the-tab book；随后演示拉拉页。')]))
    result[-1]['series']='Maisy'
    result.append(base('love-you-forever','Love You Forever','Robert Munsch',
        'https://robertmunsch.com/book/love-you-forever',
        'https://robertmunsch.com/wp-content/uploads/2011/10/1261666665love-you.jpg',
        None,[evidence(12,189,267,'spoken-title','266秒正封书名与作者、绘者可读。')]))
    result[-1]['illustrator']='Sheila McGraw'
    result.append(base('my-car','My Car','Byron Barton',
        'https://www.harpercollins.com/products/my-car-byron-barton',
        'https://www.publishersweekly.com/cover/9780060296247',
        '9780060296247',[evidence(8,666,690,'visible-cover','666秒封面书名与Byron Barton作者可读，随后翻页朗读。')]))
    result[-1]['additionalSourceUrl']='https://www.publishersweekly.com/978-0-06-029624-7'
    result[-1]['editionNote']='课程展示黄色封面纸板版；书名作者已确认。封面来自Publishers Weekly所列出版版本，课程实物ISBN未确认。'
    return result

def archive(book):
    path='media/book-covers/'+book['id']+'.jpg'
    if (ROOT/Path(path).with_suffix('.webp')).exists():path=str(Path(path).with_suffix('.webp'))
    if book['id'] in ['put-me-in-the-zoo','a-fly-went-by','big-purple-book','very-hungry-caterpillar'] and (ROOT/path).exists():
        size=subprocess.run(['sips','-g','pixelWidth','-g','pixelHeight',str(ROOT/path)],capture_output=True,text=True).stdout
        if 'pixelWidth: 1200' in size and 'pixelHeight: 630' in size:
            (ROOT/path).rename(RESEARCH/(book['id']+'-social-card.jpg'))
    asset=download(book['coverSourceUrl'], path, referer=book['sourceUrl'])
    signature=(ROOT/path).read_bytes()[:12]
    if signature.startswith(b'RIFF') and signature[8:12]==b'WEBP' and path.endswith('.jpg'):
        new_path=str(Path(path).with_suffix('.webp'));(ROOT/path).rename(ROOT/new_path);path=new_path
    out=subprocess.run(['sips','-g','pixelWidth','-g','pixelHeight',str(ROOT/path)],capture_output=True,text=True,check=True).stdout
    width=int(re.search(r'pixelWidth: (\d+)',out).group(1));height=int(re.search(r'pixelHeight: (\d+)',out).group(1))
    book['cover']=path
    book['note']=book['editionNote']
    book['coverMetadata']={'width':width,'height':height,'bytes':asset['bytes'],'sha256':asset['sha256'],'selection':'作者或出版社页面所提供的封面文件。'}
    return book

def main():
    import os
    os.chdir(ROOT)
    books=records(); output={};errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(archive,b):i for i,b in enumerate(books)}
        for f in as_completed(jobs):
            i=jobs[f]
            try:output[i]=f.result();print('Saved',output[i]['title'],flush=True)
            except Exception as e:errors.append({'id':books[i]['id'],'error':type(e).__name__});print('Failed',books[i]['title'],type(e).__name__,flush=True)
    path=ROOT/'metadata/book-additional-mentions.json'
    old=json.loads(path.read_text()) if path.exists() else {}
    old.update(checkedAt=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),books=[output[i] for i in sorted(output)],downloadErrors=errors)
    path.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    print('Total',len(output),'errors',len(errors))

if __name__=='__main__':main()
