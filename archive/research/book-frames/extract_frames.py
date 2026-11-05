from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess
root=Path.cwd();out=root/'.private/book-frames'
groups={
 '01-mess':('media/videos/01_母语.mp4',[515,518,521,524,527,530,533]),
 '03-spot':('media/videos/03_兴趣.mp4',[459,464,470,474,480,486,492,498,500]),
 '04-sleep':('media/videos/04_对父母的挑战.mp4',[466,470,474,478,482,486,488]),
 '13-red':('media/videos/13_绘本的使用.mp4',[324,330,340,350,365,380,395,402]),
 '12-mum':('media/videos/12_许瞧的闺房.mp4',[161,162,163,164]),
 '08-car':('media/videos/08_读.mp4',[664,666,668,692]),
 '12-anthony':('media/videos/12_许瞧的闺房.mp4',[144,146,148,150,152,156,160,164,166,168,170,172]),
 '12-love':('media/videos/12_许瞧的闺房.mp4',[188,190,192,196,198,260,264,266,268]),
 '12-maisy':('media/videos/12_许瞧的闺房.mp4',[884,888,892,896,900,902,904,906,908,910,946,950,954,958]),
 '13-spot':('media/videos/13_绘本的使用.mp4',[516,520,524,528,532,536,540,544,548,552]),
 '08-unknown':('media/videos/08_读.mp4',[670,674,678,682,686,690,1272,1280,1296,1312,1320]),
}
def extract(item):
 group,path,t=item;p=out/f'{group}-{t:04d}.jpg'
 if not p.exists(): subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(t),'-i',str(root/path),'-frames:v','1','-q:v','2','-y',str(p)],check=True)
 return p
with ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(extract,[(g,p,t) for g,(p,ts) in groups.items() for t in ts]))
for group,(_,times) in groups.items():
 files=[str(out/f'{group}-{t:04d}.jpg') for t in times]
 subprocess.run(['magick','montage','-font','/System/Library/Fonts/Supplemental/Arial.ttf','-pointsize','14','-label','%f',*files,'-tile','3x','-geometry','480x270+0+4','-background','white',str(out/f'{group}-contact.jpg')],check=True)
print('extracted',sum(len(ts) for _,ts in groups.values()),'frames')
