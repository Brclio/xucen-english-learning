# Cloudflare Pages 免费静态部署

线上使用 **Cloudflare Pages 静态网页 + 公开 GitHub Release 视频**。不使用 R2、Workers、Pages Functions 或收费依赖，网页运行不需要服务端密钥。仓库和 Release 为公开内容；此方案不提供密码保护。

原来的 `index.html`、课程数据、41 个 MP4、41 个 MP3、图片和 Markdown 保持离线版原样。`npm run build` 只生成单独的 `dist/` 在线副本，不改动、读取或还原视频文件。

## 已绑定的 GitHub 自动部署项目

当前实际使用 **Git 集成**，由 Cloudflare 拉取 GitHub 仓库、在云端构建并发布，无需本机上传 `dist`。

- 站点地址：[https://xucen-english-course.pages.dev](https://xucen-english-course.pages.dev)
- Pages 项目：`xucen-english-course`
- GitHub 仓库：`Brclio/xucen-english-learning`
- 生产分支：`main`，已开启推送后的自动部署。
- 运行方式：纯静态 Pages，没有 Functions、Workers 或 R2 绑定。
- 自定义域名与 DNS 未配置，由你自行处理。

已配置的构建参数：

| 配置 | 值 |
| --- | --- |
| Framework preset | None |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | 仓库根目录 |
| Environment variable | `NODE_VERSION=22` |
| Preview deployments | 关闭，仅发布 `main` |

项目没有 npm 第三方依赖。构建不运行 `media:restore`，也不下载 Release 视频；只读取映射文件并生成在线副本。后续更新提交并推送到 `main` 即可，由 Cloudflare 自动构建；在 Pages 控制台 **Deployments** 可查看构建进度与日志，必要时重试对应提交。

连接现有 GitHub 应用只使用本仓库，未扩大到其他私有仓库权限。配置依据 [Cloudflare 静态 HTML 文档](https://developers.cloudflare.com/pages/framework-guides/deploy-anything/) 和 [GitHub 集成文档](https://developers.cloudflare.com/pages/configuration/git-integration/github-integration/)。

## 在线版内容从哪里读取

| 内容 | 在线来源 | 完整文件是否保留 |
| --- | --- | --- |
| 41 个完整 MP4 | 公开 GitHub Release `course-v1` | 本地原文件、源码归档和 Release 均保留 |
| 41 个 MP3 | Cloudflare Pages 静态资源 | 原样复制，无压缩和转码 |
| 课程图片、绘本封面、文字与 Markdown | Cloudflare Pages 静态资源 | 原样复制；在线 Markdown 的视频链接改为 Release |
| 学习进度、笔记、播放位置 | 当前浏览器 localStorage | 可从学习页面导出笔记 |

Release 视频使用稳定 ASCII 名 `lesson-00.mp4` 至 `lesson-40.mp4`。`metadata/release-file-map.json` 保存原文件、课时 ID、Release 文件名、URL、大小和 SHA-256 的一一对应关系。显示课名仍使用原名称；更换线上文件名不会改变视频内容。

播放器示例地址：

```text
https://github.com/Brclio/xucen-english-learning/releases/download/course-v1/lesson-00.mp4
```

构建会严格验证映射与课程目录匹配，仅在 `dist/course-data.js` 和 `dist/course-data.json` 中替换 `videoPath`。`dist/app.js` 只放行本课程映射中的 41 个精确 Release URL；原始 `app.js` 继续只接受本地媒体路径。绘本书架中的课程时码链接仍跳转到同一播放器。

Cloudflare Pages 单文件上限为 25 MiB。当前最大 MP3 为 21,270,822 字节（约 20.29 MiB），全部音频都在限制内；构建会检查每个静态文件并拒绝超限文件。视频和源码分卷不放入 `dist`。[Pages 官方限制](https://developers.cloudflare.com/pages/platform/limits/)

## 本机构建与检查

```sh
npm test
npm run build
```

构建全程离线，不需要 GitHub API 凭据或 Cloudflare 登录。`dist/` 包含网页、41 个音频、图片、课程 Markdown 和页面引用的公开核查资料，不包含 MP4、视频分卷、`.private/`、开发脚本或凭据。构建报告在 `.private/pages-build-report.json`。

可用任意静态服务器预览。例如已安装 Python 3 时：

```sh
python3 -m http.server 8787 --directory dist
```

浏览器打开 `http://127.0.0.1:8787`。在线视频需要联网访问公开 Release；本地学习仍直接打开源码根目录的 `index.html`。普通 Git 克隆后的 4 个大视频需要离线还原时，再执行：

```sh
npm run media:restore
```

这条还原命令仅服务本地离线使用，Cloudflare 构建与在线播放不需要执行。

## Release 更新

先将所有完整 MP4 上传至公开的 `course-v1` Release，并确保映射中的文件名可访问，再部署 Pages。视频未上传、Release 为草稿/私有或资产被删除时，网页无法从该地址播放；源码中的离线视频不受影响。

若将来更换仓库或 Release tag，需要同步调整构建脚本中的 `RELEASE_BASE` 和 `metadata/release-file-map.json`，重新运行测试和构建。线上浏览器直接读取 GitHub 的媒体响应；视频传输、Range 支持与可用性由 GitHub Release 服务提供，Cloudflare 不代理视频流。
