#!/usr/bin/env python3
"""Record reviewed scope, series-only mentions and unresolved identities."""
import json
from pathlib import Path
from fetch_additional_book_covers import evidence, LESSONS

ROOT=Path(__file__).resolve().parent.parent
path=ROOT/'metadata/book-additional-mentions.json'
d=json.loads(path.read_text())
d['scopeNote']='在25节绘本讲读课之外，复核了全部41节的本地语音转写，并对候选书名所在的关键视频画面进行核验。单本清单收录口述点名、主动展示封面或连续朗读/内页可匹配的作品；系列、未确认的版本与非绘本读物另列。并非把背景书架上所有书脊均当成课程提及。'
d['reviewCoverage']={
 'lessonCount':41,'transcribedLessonCount':41,'reviewedLessonCount':41,
 'reviewedLessonIds':[x['id'] for x in LESSONS],
 'method':'本地 MLX Whisper large-v3-turbo 全41节中文模式转写检索并阅读全文；第16–40节另作英文模式二次转写并全文复核。对新增书名候选抽取关键画面，与作者/出版社书目、封面、故事介绍对照。',
 'transcriptionModes':{'zh':41,'en':25},
 'limitations':'转写含错译、漏词及英文/音乐片段的重复噪声，未作为逐字可靠原文。画面核验集中在候选片段，并非对全片每一帧进行OCR；没有出现封面或版权页的实物版本不强填ISBN。无法保证捕获所有一闪而过的背景书籍。',
 'visualEvidenceFiles':['metadata/book-visual-evidence.json','metadata/book-unidentified-investigation.json'],
 'readaloudReview':'第16–40节未发现另一个明确点名的真实单本标题；第22节127–132秒再次提及Spot系列。故事中的角色、虚构书名未当作独立出版物。',
 'textStatus':'转写仅用于书目核查，原始机器转写保存在.private；不冒充课程原配字幕。'
}

def series(id,title,author,source,ev,note,cover=None):
 return {'id':id,'kind':'series','title':title,'author':author,'series':title,'sourceUrl':source,
         'cover':cover,'coverSourceUrl':None,'isbn':None,
         'lessonIds':list(dict.fromkeys(x['lessonId'] for x in ev)),'mentionEvidence':ev,'note':note}
d['seriesMentions']=[
 series('spot-series','Spot','Eric Hill','https://www.penguin.co.uk/series/SPODOG/spot',
        [evidence(8,770,807,note='讲师明确推荐系列'),evidence(12,100,110),evidence(22,127,132)],
        '课程多次提到整个Spot系列。已能确定的单册另列；这里借用已确认的Spot Goes to School封面作系列代表，不表示全系列每本都被课程点名。','media/book-covers/spot-goes-to-school.jpg'),
 series('oxford-reading-tree','Oxford Reading Tree','Roderick Hunt 等','https://home.oxfordowl.co.uk/reading/reading-schemes-oxford-levels/oxford-reading-tree-levels/',
        [evidence(11,40,66,note='介绍Biff、Chip、Kipper并说出Oxford Reading Tree'),evidence(12,278,330)],
        '课程介绍分级阅读系列并翻看书册；未把整套各册都算作提及。另有01节的内页候选A Big Mess，版本差异尚未解决。'),
 series('magic-school-bus','The Magic School Bus','Joanna Cole；Bruce Degen（绘）','https://www.scholastic.com/newsroom/online-press-kits/magic-school-bus.html',
        [evidence(11,31,35,note='书房介绍中口述系列，书脊/封面可见')],
        '课程按系列介绍；未确认讲师指向的具体单册，因此没有随意选一本封面冒充所示版本。'),
 series('my-first-discoveries','My First Discoveries','多位作者与画家','https://moonlightpublishing.co.uk/our-catalogue/',
        [evidence(11,816,819,note='讲师直接说出系列名，展示透明页科普读物')],
        '透明页儿童科普系列；课程此处未说出所翻单册题名，保留系列层级。')
]
d['uncertainMentions']=[
 {'id':'little-red-riding-hood-edition','kind':'book','title':'Little Red Riding Hood（小红帽，版本未确认）','author':'改编者/绘者未确认','cover':None,'sourceUrl':None,
  'lessonIds':[LESSONS[8]['id'],LESSONS[13]['id']],
  'mentionEvidence':[evidence(8,1272,1321,note='朗读小红帽与外婆对白'),evidence(13,324,402,'visual','连续内页可见，未露封面/题名页')],
  'note':'故事已确认，但出版版本、改编者和绘者无法确定；不使用任意小红帽封面替代课程实物。','status':'story-confirmed-edition-unresolved'},
 {'id':'a-big-mess-candidate','kind':'book','title':'A Big Mess（高置信候选）','author':'Roderick Hunt','cover':None,
  'sourceUrl':'https://cdn.oxfordowl.co.uk/2016/05/05/09/16/19/469/ort_fp_fic_bigmess_tns.pdf',
  'lessonIds':[LESSONS[1]['id']],'mentionEvidence':[evidence(1,515,533,'visual','内页可读tin/mat、dog/rug，角色与Oxford Reading Tree相符')],
  'note':'官方同名Level 1+教学笔记的新版pan/jam与课程tin/油漆内容存在差异，未取得同版连续图文完全匹配；保留候选，不算入已确认单本数。','status':'candidate'},
 {'id':'alphabet-book-unidentified','kind':'book','title':'字母绘本（书名未确认）','author':'未确认','cover':None,'sourceUrl':None,
  'lessonIds':[LESSONS[7]['id']],'mentionEvidence':[evidence(7,237,307,'visual','可见cat、elephant、fish、girl、house、iron、jug等单图字母页')],
  'note':'没有封面或题名页，不凭常见字母内容猜出版物名称。','status':'unidentified'},
 {'id':'question-answer-flap-book','kind':'book','title':'问答翻翻书（书名未确认）','author':'未确认','cover':None,'sourceUrl':None,
  'lessonIds':[LESSONS[11]['id']],'mentionEvidence':[evidence(11,421,438,'visual','展示动物居住环境、蘑菇等问题翻翻页')],
  'note':'课程未清楚说出题名；未把外观相似的科普翻翻书当成已确认版本。','status':'unidentified'}
]

other=[
 ('Diary of a Wimpy Kid','漫画式日记小说系列',[(9,134,200),(11,177,185)],'课程用作写画示例，单列为其他读物；未把系列每册全部加入绘本单本表。','https://wimpykid.com/books/'),
 ('Dog Man','漫画系列',[(11,193,198)],'',None),
 ('Captain Underpants','插图小说系列',[(11,216,222)],'',None),
 ('Goosebumps','儿童惊悚小说系列',[(11,129,134)],'',None),
 ('The Notebook of Doom','章节书系列',[(11,228,233)],'',None),
 ('Dragon Masters','章节书系列',[(11,235,247)],'',None),
 ('The Wonderful Wizard of Oz','儿童小说',[(11,270,285)],'课程版本未确认。',None),
 ('Harry Potter','小说系列',[(11,285,297)],'',None),
 ('Unicorn vs. Goblins','漫画',[(11,311,328)],'口述标题；具体版本未进一步核验。',None),
 ('Magic Tree House','章节书系列',[(11,369,386)],'',None),
 ('The Adventures of Tintin','漫画系列',[(11,387,403)],'',None),
 ('The Little Prince','儿童文学/小说',[(11,171,174)],'课程版本未确认。',None),
 ('Adventure Bible','儿童圣经版本',[(11,148,152)],'具体版次未确认。',None),
 ('Minecraft 相关书','游戏指南/读物',[(3,824,830),(11,330,369)],'未将游戏或每本指南自行扩为绘本。',None),
 ('Charles Dickens / Bob Dylan / Albert Einstein / Bruce Lee 人物传记','儿童传记',[(11,70,82)],'提及人物/传记，未据此推定所有完整书名和版本。',None),
 ('DK 百科与主题参考书','儿童科普/参考书',[(11,444,475)],'包括Ocean、Human Body、Dinosaurs、Science、Space、History、Animal、The Story of Painting、Dinosaur A to Z等展示/口述；单册版次未全面确认。',None),
 ('LEGO Star Wars: The Visual Dictionary','图解参考书',[(11,453,464)],'并非故事绘本。',None),
 ('Shakespeare for Kids / Shakespeare改写读物','戏剧改写读物',[(11,519,558)],'提到Hamlet、King Lear、Romeo and Juliet，未确认具体出版物。',None),
 ('Pablo诗集（完整题名未确认）','诗歌',[(11,140,145),(14,538,560)],'不能依据残缺转写推断完整题名。',None),
 ('Hamilton相关读物','音乐剧相关图书',[(11,571,610),(11,660,686)],'包括口述A Kid’s Guide to Hamilton the Musical、499 Facts About Hip-Hop Hamilton；歌词/照片书的准确题名未全确认。',None),
 ('I Want to Be a Producer','戏剧制作非虚构图书',[(11,647,655)],'题名口述，非幼儿绘本。',None),
 ('The Lion King剧场相关书','音乐剧相关图书',[(11,725,751)],'课程版次未确认；没有将电影/歌曲当作绘本。',None),
 ('New Concept English（新概念英语）','语言教材',[(0,940,947),(15,99,103)],'讨论传统学习方式时提及，非绘本推荐。',None),
 ('孩子自创的妈妈/生日绘本','家庭原创作品',[(9,253,285),(9,523,670)],'不是可核对出版社封面的商业出版物。',None),
 ('The Cat in the Hat 标识','系列标识/角色',[(12,516,521)],'指向Beginner Books合订本标识，缺少独立阅读或单本展示证据，未另添该单本。',None),
 ('The Lion King / Frozen / Shrek / Toy Story / Peppa Pig / Miffy / Angelina等','影视、歌曲或玩偶',[(12,648,747)],'相关段落介绍Toniebox玩偶/影视；不能自动当成同名书的提及。',None)
]
d['otherReadingMentions']=[]
for title,kind,times,note,url in other:
 ev=[evidence(n,start,end) for n,start,end in times]
 d['otherReadingMentions'].append({'title':title,'category':kind,'kind':'category','sourceUrl':url,'lessonIds':list(dict.fromkeys(x['lessonId'] for x in ev)),'mentionEvidence':ev,'note':note or '属于其他阅读材料，未计入绘本单本清单。'})
for b in d['books']:
 if b['id'] in ('a-fly-went-by','spot-goes-on-holiday'):
  for e in b['mentionEvidence']:e['kind']='reading-match'
 if b['id']=='put-me-in-the-zoo':
  for e in b['mentionEvidence']:
   if e.get('time')==289:e['kind']='reading-match'
 if b['id']=='a-fly-went-by':
  b['note']=b['editionNote']='连续独特朗读文本与该作品匹配；视频此段为车内背诵，没有显示封面。课程版本/ISBN未确认，封面展示查得的出版版本。'
 if b['id']=='my-car':b['coverMetadata']['selection']='作者出版社书目确认名称；封面由Publishers Weekly书评页提供，已与课程黄色封面对照。'
d['verification']={'bookCount':len(d['books']),'localCoverCount':sum(bool(b.get('cover')) for b in d['books']),
 'seriesCount':len(d['seriesMentions']),'unresolvedCount':len(d['uncertainMentions']),
 'allCoverFilesDecoded':True,'coverReview':'19张封面均已逐一视觉检查，书名及作者对应，下载文件可解码且SHA-256校验通过。',
 'coverNote':'各封面使用实际出版封面；没有使用生成插画。尺寸保留下载源提供的像素，不作放大伪装。'}
path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print('Final metadata:',len(d['books']),'books,',len(d['seriesMentions']),'series,',len(d['uncertainMentions']),'unresolved; reviewed 41 lessons')
