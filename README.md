# 许岑的英语启蒙方法论 · 本地学习资料

打开 [index.html](index.html) 即可进入学习网页，无需联网、安装依赖或启动服务器。

## 从 GitHub 取得完整课程

公开仓库：[Brclio/xucen-english-learning](https://github.com/Brclio/xucen-english-learning)。本仓库使用普通 Git，不依赖 Git LFS。

```sh
git clone https://github.com/Brclio/xucen-english-learning.git
cd xucen-english-learning
node scripts/restore_media.mjs
```

37 个视频、41 个音频、全部课程图片与绘本封面直接保存在源码目录。另 4 个视频超过 GitHub 的单文件 100 MiB 限制，其**全部原始字节**保存在 `media/video-parts/` 的 9 个无损分卷中；上述还原命令会按 `media/large-files.json` 验证并拼回原路径。没有转码或降低清晰度。原文件已存在时只做校验，内容不符时停止，绝不覆盖。

本机现有 41 个完整视频仍在 `media/videos/`，不需要重新下载。全部 41 个完整 MP4 同时提供于 [课程视频 Release](https://github.com/Brclio/xucen-english-learning/releases/tag/course-v1)，下载即可播放。Release 使用稳定文件名 `lesson-00.mp4` 至 `lesson-40.mp4`，显示标签保留原课名；[文件名对应表](metadata/release-file-map.json)记录原路径与 SHA-256，内容没有改变。Release 视频是本项目已经保存的 720p 课程文件，不代表尚未找到的上传原片。

完成还原后，直接打开 `index.html`。Node.js 只用于分卷还原和部署工具，日常离线学习无需启动服务器。

## Cloudflare 免费部署

见 [CLOUDFLARE.md](CLOUDFLARE.md)。使用 Cloudflare Pages 纯静态站，无需 R2、Workers 或付费服务。构建命令为 `npm run build`，输出目录为 `dist`。线上版视频读取本仓库公开 Release 中的完整 MP4；音频、图片、封面及文字资料由 Pages 静态托管。构建只生成部署副本，现有离线网页、课程数据和本地媒体保持不变。

研究过程的机器转写、抽帧和源码证据保存在 [archive/](archive/README.md)。原始访问凭据只留在本机；提交的研究副本已脱敏，所有课程音视频保持原样。

[绘本书架](books.html)收录课程中已核实的绘本及系列，封面保存在本地；可搜索书名、查看提及证据，并跳转到课程对应时间。[绘本书目.md](绘本书目.md)提供同一书目的 Markdown 版本。

## 实际保存情况

- 目录共 41 节；已保存本地视频 41 个、独立音频 41 个、图片 7 张。
- 已保留课程介绍原文及每节课的 Markdown 索引；当前课时接口未列出独立课文、字幕或课件附件。

更新时间：2026-11-05T19:10:48+08:00

[原课程页面](https://appuzenkpej8854.h5.xet.pomoho.com/p/course/column/p_673aa9b1e4b023c058a64b53)

## 如何学习

1. 打开 `index.html`，在课程目录中选课。可搜索名称、按类型或保存状态筛选。
2. 播放本地音频或视频；浏览器会记住播放位置。
3. 点击「标记学完」保存学习进度。在「学习笔记」里记录并导出 Markdown。
4. [课程介绍.md](课程介绍.md) 保存原页面课程介绍；[课程目录.md](课程目录.md) 汇总所有课程入口。
5. `lessons/` 下的 41 份 Markdown 是每课资料索引。当前课时接口未提供正文或字幕；这些索引不是视频逐字稿。

学习进度、笔记和播放位置保存在当前浏览器。清理浏览器数据、更换浏览器或移动文件夹可能影响记录，请先导出笔记。视频播放速度可通过浏览器播放器菜单设置。

## 文件位置

- `media/audio/`：平台提供的独立音频文件。
- `media/videos/`：已成功保存的视频（以各课链接及视频清单为准）。
- `media/images/`：课程封面和原页面图片。
- `media/book-covers/`：课程书目对应的本地封面。
- `books-data.json` / `books-data.js`：绘本书目、封面来源和课程提及位置。
- `metadata/original-source-deep-investigation.md`：上传原片与清晰度深查，包含真实接口、上传素材对象逻辑和备用线路媒体字节比较的结论。
- `lessons/`：逐课 Markdown 索引。
- `metadata/assets-manifest.json`：音频和图片文件大小、SHA-256 与媒体元数据。
- `metadata/videos-manifest.json`：视频清单（取得视频后生成）；以实际路径、清晰度及校验信息为准。
- `metadata/course-summary.txt`：课程简介的原始纯文本。
- `metadata/course-description.txt`：商品详情纲要的原始纯文本。
- `course-data.json` / `course-data.js`：学习网页使用的本地目录数据。
- 学习网页总览的「课程资料」提供课程介绍、完整目录、视频清晰度核验说明（生成后）及全部原页面图片的下载入口。

## 重新生成目录

新增媒体后，先更新对应的 manifest，再执行：

```sh
python3 scripts/build_catalog.py
python3 scripts/build_books.py
```

默认会将尚无本地视频的条目标为「待完成」。只有在确认最终限制后，才使用 `--video-fallback-state drm` 或 `--video-fallback-state failed`。视频清单内每课的状态优先于此参数。脚本仅引用实际存在、大小匹配的本地文件，不从受保护的视频地址推断下载成功。

`.private/` 存放采集过程需要的私有响应，可能含短期访问凭据；学习网页不使用它。分享学习网页文件时不包含该目录。

## 绘本与上传原片的核查范围

绘本整理覆盖课程目录、41 课本地语音识别辅助审阅，以及重点片段的实际画面核对。机器识别存在误听与重复，未作为官方逐字稿发布；版本无法确认的书目会单独注明，不用猜测的封面补齐。封面的出版版本及来源见每项说明。

当前学员账号可取得的最高视频档位是 1280×720。本次进一步追查了播放器依赖源码、真实素材标识、旧版多云播放接口、上传素材回查逻辑和实际解密后的媒体分片。尚未找到可访问的上传原片；不能据此断言上传原片只有 720p 或服务器没有保留原片。详见[深查记录](metadata/original-source-deep-investigation.md)。
