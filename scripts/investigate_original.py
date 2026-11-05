"""Collect provenance from literal served module dependencies and authorized URLs.
No guessed bucket paths or privileged/admin calls.
"""
from pathlib import Path
import re,json,hashlib,time,concurrent.futures as cf
from urllib.parse import urljoin,urlsplit,urlunsplit
import subprocess
import requests
BASE=Path(__file__).resolve().parents[1]
DIR=BASE/'.private/quality-research/deep';DIR.mkdir(parents=True,exist_ok=True)
ENTRY='https://assets.cdn.xiaoeknow.com/course/h5_study_fe/1.4.70/js/BasicVideo-legacy.js'

def fetch_js(url):
 name=hashlib.sha256(url.encode()).hexdigest()[:10]+'-'+urlsplit(url).path.rsplit('/',1)[-1]
 p=DIR/name
 if not p.exists():
  for attempt in range(4):
   try:
    r=requests.get(url,timeout=30);r.raise_for_status();p.write_bytes(r.content);break
   except requests.RequestException:
    if attempt==3:raise
    time.sleep(attempt+1)
 s=p.read_text();m=re.search(r'System\.register\((\[.*?\]),',s)
 imports=json.loads(m[1])if m else []
 refs=[urljoin(url,i)for i in imports if i.endswith('.js')]
 # Include only literal generated module references in the served source.
 refs+= [urljoin(url,i)for i in re.findall(r'\.import\(["\'](\.{1,2}/[^"\']+\.js)["\']',s)]
 endpoints=sorted(set(re.findall(r'(?:https?://|/xe\.)[A-Za-z0-9_./?=:$-]+',s)))
 hits=[]
 for match in re.finditer(r'(?i)(origin(?:al)?[_A-Za-z]*url|source[_A-Za-z]*url|material[_A-Za-z]*info|(?:original|origin)_file|(?:download|export)[_A-Za-z]*url|/xe\.[A-Za-z0-9_./-]+)',s):
  a,b=match.span();hits.append({'term':match[0],'offset':a,'context':s[max(0,a-160):b+230]})
 return {'url':url,'local':str(p.relative_to(BASE)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'imports':sorted(set(refs)),'endpoints':endpoints,'hits':hits}

def collect(depth=2):
 seen={};queue=[ENTRY]
 for level in range(depth+1):
  todo=list(dict.fromkeys(u for u in queue if u not in seen));queue=[]
  with cf.ThreadPoolExecutor(max_workers=6)as pool:
   for result in pool.map(fetch_js,todo):
    seen[result['url']]=result;queue+=result['imports']
  (DIR/'modules-partial.json').write_text(json.dumps({'entry':ENTRY,'depth':level,'modules':list(seen.values())},ensure_ascii=False,indent=2))
  print('level',level,'modules',len(seen),'bytes',sum(x['bytes']for x in seen.values()),flush=True)
 out={'entry':ENTRY,'depth':depth,'modules':list(seen.values())};(DIR/'modules.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 return out
def public_url(url):
 p=urlsplit(url);return urlunsplit((p.scheme,p.netloc,p.path,'',''))

def fetch_read(url):
 for attempt in range(3):
  try:
   r=requests.get(url,timeout=(12,30));r.raise_for_status();return r
  except requests.RequestException:
   if attempt==2:raise RuntimeError('HTTP or transport failed for '+public_url(url))from None
   time.sleep(attempt+1)

def compare_cloud_routes():
 """Read only URLs returned by the legacy multi_line response; compare samples.
 No guessed rendition names, bucket paths, or upload credentials are used.
 """
 from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
 records=json.loads((BASE/'.private/quality-research/multi-line-raw.json').read_text())
 out=[]
 for record in records:
  row={'resourceId':record['id'],'routes':{}}
  for platform,route in record['response']['data']['cloud_data'].items():
   url=route['encrypt_url'];r=fetch_read(url);s=r.text
   assert s.startswith('#EXTM3U')
   lines=s.splitlines();sequence=0;key=None;iv=None;segments=[];keys={}
   for line in lines:
    if line.startswith('#EXT-X-MEDIA-SEQUENCE:'):sequence=int(line.split(':')[1])
    elif line.startswith('#EXT-X-KEY:'):
     if 'METHOD=NONE' in line:key=None;iv=None;continue
     assert 'METHOD=AES-128' in line
     key_url=urljoin(url,re.search(r'URI="([^"]+)"',line)[1])
     if key_url not in keys:
      kr=fetch_read(key_url);keys[key_url]=kr.content
     key=keys[key_url];assert len(key)==16
     match=re.search(r'IV=0x([0-9a-fA-F]+)',line);iv=int(match[1],16).to_bytes(16,'big')if match else None
    elif line and not line.startswith('#'):
     segments.append((urljoin(url,line),key,iv or sequence.to_bytes(16,'big')));sequence+=1
   item={'url':public_url(url),'status':r.status_code,'playlistBytes':len(r.content),'isMaster':'#EXT-X-STREAM-INF' in s,'segments':len(segments),'duration':sum(map(float,re.findall(r'#EXTINF:([\d.]+)',s))),'headers':{k:v for k,v in r.headers.items()if k.lower()in ['content-type','etag','last-modified','server','content-disposition']},'samples':[]}
   for idx in sorted(set([0,len(segments)//2,len(segments)-1])):
    seg_url,key,iv=segments[idx]
    try:sr=fetch_read(seg_url)
    except RuntimeError as err:
     item['samples'].append({'index':idx,'url':public_url(seg_url),'error':str(err)});continue
    payload=sr.content
    sample={'index':idx,'url':public_url(seg_url),'encryptedBytes':len(payload),'encryptedSHA256':hashlib.sha256(payload).hexdigest()}
    if key:
     cipher=Cipher(algorithms.AES(key),modes.CBC(iv)).decryptor();payload=cipher.update(payload)+cipher.finalize()
     pad=payload[-1]
     if 0<pad<=16 and payload[-pad:]==bytes([pad])*pad:payload=payload[:-pad]
    sample['plainSHA256']=hashlib.sha256(payload).hexdigest();sample['plainBytes']=len(payload)
    probe=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json','-i','pipe:0'],input=payload,capture_output=True,check=True)
    sample['streams']=[{k:v for k,v in st.items()if k in ['codec_name','codec_type','width','height','profile','pix_fmt','sample_rate','channels']}for st in json.loads(probe.stdout)['streams']]
    item['samples'].append(sample)
   row['routes'][platform]=item
  routes=list(row['routes'].values())
  row['sameSamplePlainPayloads']=(len({tuple(s.get('plainSHA256')for s in route['samples'])for route in routes})==1)if all('plainSHA256'in s for r in routes for s in r['samples'])else None
  row['sameSegmentCountAndDuration']=len({(r['segments'],r['duration'])for r in routes})==1
  out.append(row)
  print(record['id'],'routes',list(row['routes']),'identicalPlainSamples',row['sameSamplePlainPayloads'],flush=True)
 (BASE/'metadata/original-source-alternate-routes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 return out

def build_report():
 raw=json.loads((BASE/'.private/course-raw.json').read_text())
 play=json.loads((BASE/'.private/playback-raw.json').read_text())
 modules=json.loads((DIR/'modules.json').read_text())['modules']
 routes=json.loads((BASE/'metadata/original-source-alternate-routes.json').read_text())
 samples=json.loads((BASE/'metadata/original-source-provenance-samples.json').read_text())
 repo_sources=json.loads((DIR/'repos/sources.json').read_text())
 known={m['url']for m in modules};linked={u for m in modules for u in m['imports']}
 mappings=[]
 for lesson,p in zip(raw['lessons'],play['lessons']):
  assert lesson['id']==p['id']
  info=lesson['detail']['data']['video_info'];item=p['play']
  mappings.append({'resourceId':lesson['id'],'title':p['title'],'materialId':info['material_id'],'returnedMaterialId':item['material_id'],'materialAppId':info['material_app_id'],'originalFilenameField':info['file_name'],'isTranscode':info['is_transcode'],'isDRM':info['is_drm'],'playVariants':list(item['play_list']),'videoURLWithoutSignature':public_url(item['play_list']['720p_hls']['play_url']),'sourceWidth':None,'sourceHeight':None,'sourceObject':None,'sourceRetained':None})
 assert all(x['sameSamplePlainPayloads'] and x['sameSegmentCountAndDuration']for x in routes)
 media_samples=[s for r in routes for v in r['routes'].values()for s in v['samples']]
 dimensions=sorted({(s['width'],s['height'])for item in media_samples for s in item['streams']if s['codec_type']=='video'})
 relevant=[]
 terms={
 'BasicVideo-legacy.js':['/xe.material-center.play/getPlayUrl','https://material-api.xiaoeknow.com/api/xe.keyframes/get/1.0.0'],
 'main-legacy-68127257.js':['/xe.course.business_go.video.mutli_line/1.0.0'],
 'OldVideoContent-legacy.js':['getVideoExchangeRouteList','cloud_data'],
 'xiaoe-jssdk-legacy.js':['/xe.material-center.platform.asset.details.get/1.0.0','source_bucket:t.obsBucket','getUploadPath=function','Date.now().toString(36)+Math.random()']}
 for m in modules:
  name=urlsplit(m['url']).path.rsplit('/',1)[-1]
  if name in terms:
   code=(BASE/m['local']).read_text()
   relevant.append({k:m[k]for k in ['url','local','sha256','bytes']}|{'codeEvidence':[{'term':term,'offset':code.find(term)}for term in terms[name]]})
 result={'status':'authorized learner playback fully inspected; uploaded original unresolved','accountScope':'User confirmed purchased learner access only; no merchant upload/material-management access','moduleGraph':{'count':len(modules),'bytes':sum(m['bytes']for m in modules),'unfetchedLiteralImports':len(linked-known),'entry':ENTRY},'allLessons':mappings,'alternateRouteAudit':{'lessons':len(routes),'routesPerLesson':2,'sampledSegmentsPerRoute':3,'segmentsDecoded':len(media_samples),'dimensions':dimensions,'allSamplePayloadPairsIdentical':True,'evidence':'original-source-alternate-routes.json'},'provenanceSamples':'original-source-provenance-samples.json','sourceCodeEvidence':relevant,'publicImplementationSources':repo_sources,'sourceMetadataReadPaths':[{'endpoint':'/xe.material-center.platform.asset.details.get/1.0.0','method':'POST','params':['source_bucket','source_object'],'usedBy':'upload SDK completion poll','responseFieldsConsumed':['asset_status','asset_id','video_url'],'queried':False,'reason':'Neither source_bucket nor source_object is present in learner responses; no source object was guessed.'},{'endpoint':'https://api.xiaoe-tech.com/xe.material.list/1.0.0','method':'POST','params':['access_token','type=3'],'permission':'素材管理-查询','documentedFields':['material_id','material_size','material_property.width','material_property.height','material_property.pixel_data'],'documentation':'https://api-doc.xiaoe-tech.com/api_list/material/list.html','queried':False,'reason':'Requires a merchant API token with material query permission; user has learner purchase access only. Documentation does not itself prove original retention or provide an original download URL.'}],'known':['41 authorized play responses expose 720p_hls and mp3 only.','Resource IDs map to 41 material IDs with original filename fields and is_transcode=1.','All archived playback video streams are 1280x720.','Four legacy multi-cloud samples resolve to media playlists and identical sampled decoded TS payloads across the two CDN routes.'],'unknown':['Whether the uploaded original file is still retained by the platform.','The uploaded original video dimensions, bitrate, and byte-level identity.','Whether a higher-resolution rendition exists outside this learner account playback response.'],'conclusion':'720p is the highest verified and downloadable rendition exposed to this learner account. It is not established that 720p is the uploader original or the only version stored by the service.'}
 (BASE/'metadata/original-source-deep-investigation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 rows='\n'.join(f"| {next(s['index']for s in samples if s['resourceId']==r['resourceId']):02d} | {next(s['filename']for s in samples if s['resourceId']==r['resourceId'])} | {next(iter(r['routes'].values()))['segments']} | 相同 | 1280×720 |"for r in routes)
 report=f'''# 上传原片与清晰度深查

本次从课程资源、素材标识、实际媒体文件和播放器依赖源码继续追查。**当前学员账号可核验、可下载的最高视频版本是 1280×720；没有找到上传原片或更高清版本的可用地址。不能据此认定上传原片就是 720p，也不能认定服务器没有保留更高版本。** 用户已确认只有学员购买权限。

## 已核验的资源链

41 个课程 `resource_id` 分别映射到 41 个 `material_id`，课程详情与实际播放响应中的素材标识相符。详情保留 `file_name`（如 `00_先导.mp4`）及 `is_transcode=1`，但不返回上传源文件的尺寸、码率、字节大小、存储桶或源对象键。原文件名只是元数据，不能证明当前 HLS 就是上传原片。

已保存的 41 个实际 `getPlayUrl` 响应均只有 `720p_hls` 与 `mp3`。HLS 地址能追到两种实际存储形式：字节云路径中的店铺/上传者/素材目录，以及华为云的 `/asset/{{asset_id}}/{{rendition_hash}}.m3u8`。这些是实际播放对象定位信息，并不包含上传源对象的位置。逐课对应关系见 [完整 JSON](original-source-deep-investigation.json)。

## 源码与真实接口

从当前页面实际使用的 [BasicVideo 模块]({ENTRY}) 沿 `System.register` 和字面量动态 import 递归读取 **{len(modules)} 个模块，{sum(m['bytes']for m in modules):,} 字节**；在这一依赖图中未抓取的字面量模块引用为 **{len(linked-known)}**。此处闭合只表示该入口的字面量模块依赖已取全，不代表平台全部源码、运行时拼接的动态路径或商家后台已检查。记录了各模块 SHA256 和关键代码偏移，没有用文件名枚举代替实际依赖。

除新版播放接口外，旧播放器还定义 `/xe.course.business_go.video.mutli_line/1.0.0`，以实际 `resource_id` 查询 `cloud_data`。登录会话已对 00、05、20、40 课成功调用，均返回 `hw`、`zj` 两路。下节是这些返回 URL 的真实媒体核验。

继续追到上传 SDK 中的 `/xe.material-center.platform.asset.details.get/1.0.0`：它以 `source_bucket`、`source_object` 轮询上传后的素材状态，读取 `asset_status`、`asset_id` 与 `video_url`。源码中的源对象是上传配置目录加上传时生成的唯一文件名；唯一名含时间与随机串，并非课程显示的文件名。学员详情和播放响应没有该桶/对象映射，因此没有拿 HLS 的 asset 路径冒充源对象，也没有调用上传签名或上传接口。此读接口未调用，原因是缺少实际源对象参数；不是一次服务端拒绝原片访问的实测。

公开的[官方素材列表 API](https://api-doc.xiaoe-tech.com/api_list/material/list.html)提供素材宽高、分辨率和大小字段，要求素材查询权限与 `access_token`。它可以在具有商家权限时进一步核对素材元数据，但当前学员登录态不是这种 API 凭证。文档也没有承诺这些字段对应原片留存，或给出原片下载地址。本次未请求商家凭证。

## 实际文件与备用线路

四个样本的新版/旧版播放清单均是完整媒体清单，不是含多分辨率子清单的 master playlist；实际读取的清单没有更高清子流引用。响应头包含常规类型、ETag、修改时间等信息，没有上传原片地址、原始尺寸或源对象元数据。关键帧接口按真实 app/material 标识返回成功，但四课均为空且未开启，也未给出额外视频对象。

对旧版接口返回的两条线路，各取首、中、尾分片，用各自清单中合法返回的 AES-128 密钥解密，并对比媒体字节 SHA256；共解密探测 **24 个分片**。每一课两线路的三组媒体字节均相同，实际视频流均为 1280×720。

| 课次 | 元数据文件名 | 清单分片数 | 两线路样本字节 | 实际尺寸 |
| --- | --- | ---: | --- | --- |
{rows}

这证明这四课的备用域名样本分发的是同一份 720p 媒体，并非另一份原片。该字节比较只覆盖这四课的首/中/尾样本，不把抽样结论冒充 41 课全部备用分片的逐字节验证。[分片哈希与探测记录](original-source-alternate-routes.json)、[清单及响应头记录](original-source-provenance-samples.json)均已保存。

## 公开实现交叉核对

核读了三份项目的一手源码，没有执行外部下载器：新[小鹅通下载器 API 客户端](https://github.com/miaoyc666/xiaoetong-video-downloader/blob/c1182f06e7bc71c45a27d62899a7a791fa40f1b2/src/xiaoet_downloader/api/client.py)同样通过详情里的播放签名获取播放列表，再选择已返回的清晰度；旧 [xiaoe_download](https://github.com/Abirdcfly/xiaoe_download/blob/master/get_xiaoe.py)取详情的 `video_hls`；[goose](https://github.com/nemoTyrant/goose/blob/master/main.go)消费已知 m3u8 并解密合并。三者均未提供从该学员课程恢复上传原片的额外素材链路。源码版本/下载 SHA256 见完整 JSON；这也不代表其他接口绝不存在。

## 结论边界

已确认的是：当前账号的 41 课播放资源完整获得，最高暴露版本为 720p；这次新增的旧多云链路与上传 SDK 调查没有带来更高清可下载对象。仍未知的是：平台是否保留上传原片、原片本身分辨率，以及是否存在不在学员播放响应中提供的其他版本。现有视频没有为本次调查而替换、重编码或放大。
'''
 (BASE/'metadata/original-source-deep-investigation.md').write_text(report)
 print('report complete',len(mappings),'lessons',len(media_samples),'segment probes',dimensions)
 return result

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--compare-routes',action='store_true');p.add_argument('--report',action='store_true');p.add_argument('--depth',type=int,default=8);args=p.parse_args()
 build_report()if args.report else compare_cloud_routes()if args.compare_routes else collect(args.depth)
