# 上传原片与清晰度深查

本次从课程资源、素材标识、实际媒体文件和播放器依赖源码继续追查。**当前学员账号可核验、可下载的最高视频版本是 1280×720；没有找到上传原片或更高清版本的可用地址。不能据此认定上传原片就是 720p，也不能认定服务器没有保留更高版本。** 用户已确认只有学员购买权限。

## 已核验的资源链

41 个课程 `resource_id` 分别映射到 41 个 `material_id`，课程详情与实际播放响应中的素材标识相符。详情保留 `file_name`（如 `00_先导.mp4`）及 `is_transcode=1`，但不返回上传源文件的尺寸、码率、字节大小、存储桶或源对象键。原文件名只是元数据，不能证明当前 HLS 就是上传原片。

已保存的 41 个实际 `getPlayUrl` 响应均只有 `720p_hls` 与 `mp3`。HLS 地址能追到两种实际存储形式：字节云路径中的店铺/上传者/素材目录，以及华为云的 `/asset/{asset_id}/{rendition_hash}.m3u8`。这些是实际播放对象定位信息，并不包含上传源对象的位置。逐课对应关系见 [完整 JSON](original-source-deep-investigation.json)。

## 源码与真实接口

从当前页面实际使用的 [BasicVideo 模块](https://assets.cdn.xiaoeknow.com/course/h5_study_fe/1.4.70/js/BasicVideo-legacy.js) 沿 `System.register` 和字面量动态 import 递归读取 **166 个模块，18,920,631 字节**；在这一依赖图中未抓取的字面量模块引用为 **0**。此处闭合只表示该入口的字面量模块依赖已取全，不代表平台全部源码、运行时拼接的动态路径或商家后台已检查。记录了各模块 SHA256 和关键代码偏移，没有用文件名枚举代替实际依赖。

除新版播放接口外，旧播放器还定义 `/xe.course.business_go.video.mutli_line/1.0.0`，以实际 `resource_id` 查询 `cloud_data`。登录会话已对 00、05、20、40 课成功调用，均返回 `hw`、`zj` 两路。下节是这些返回 URL 的真实媒体核验。

继续追到上传 SDK 中的 `/xe.material-center.platform.asset.details.get/1.0.0`：它以 `source_bucket`、`source_object` 轮询上传后的素材状态，读取 `asset_status`、`asset_id` 与 `video_url`。源码中的源对象是上传配置目录加上传时生成的唯一文件名；唯一名含时间与随机串，并非课程显示的文件名。学员详情和播放响应没有该桶/对象映射，因此没有拿 HLS 的 asset 路径冒充源对象，也没有调用上传签名或上传接口。此读接口未调用，原因是缺少实际源对象参数；不是一次服务端拒绝原片访问的实测。

公开的[官方素材列表 API](https://api-doc.xiaoe-tech.com/api_list/material/list.html)提供素材宽高、分辨率和大小字段，要求素材查询权限与 `access_token`。它可以在具有商家权限时进一步核对素材元数据，但当前学员登录态不是这种 API 凭证。文档也没有承诺这些字段对应原片留存，或给出原片下载地址。本次未请求商家凭证。

## 实际文件与备用线路

四个样本的新版/旧版播放清单均是完整媒体清单，不是含多分辨率子清单的 master playlist；实际读取的清单没有更高清子流引用。响应头包含常规类型、ETag、修改时间等信息，没有上传原片地址、原始尺寸或源对象元数据。关键帧接口按真实 app/material 标识返回成功，但四课均为空且未开启，也未给出额外视频对象。

对旧版接口返回的两条线路，各取首、中、尾分片，用各自清单中合法返回的 AES-128 密钥解密，并对比媒体字节 SHA256；共解密探测 **24 个分片**。每一课两线路的三组媒体字节均相同，实际视频流均为 1280×720。

| 课次 | 元数据文件名 | 清单分片数 | 两线路样本字节 | 实际尺寸 |
| --- | --- | ---: | --- | --- |
| 00 | 00_先导.mp4 | 521 | 相同 | 1280×720 |
| 05 | 05_听说读写的顺序.mp4 | 336 | 相同 | 1280×720 |
| 20 | 20_I_Love_MY_New_Toy.mp4 | 68 | 相同 | 1280×720 |
| 40 | 40_The_Thank_You_Book.mp4 | 101 | 相同 | 1280×720 |

这证明这四课的备用域名样本分发的是同一份 720p 媒体，并非另一份原片。该字节比较只覆盖这四课的首/中/尾样本，不把抽样结论冒充 41 课全部备用分片的逐字节验证。[分片哈希与探测记录](original-source-alternate-routes.json)、[清单及响应头记录](original-source-provenance-samples.json)均已保存。

## 公开实现交叉核对

核读了三份项目的一手源码，没有执行外部下载器：新[小鹅通下载器 API 客户端](https://github.com/miaoyc666/xiaoetong-video-downloader/blob/c1182f06e7bc71c45a27d62899a7a791fa40f1b2/src/xiaoet_downloader/api/client.py)同样通过详情里的播放签名获取播放列表，再选择已返回的清晰度；旧 [xiaoe_download](https://github.com/Abirdcfly/xiaoe_download/blob/master/get_xiaoe.py)取详情的 `video_hls`；[goose](https://github.com/nemoTyrant/goose/blob/master/main.go)消费已知 m3u8 并解密合并。三者均未提供从该学员课程恢复上传原片的额外素材链路。源码版本/下载 SHA256 见完整 JSON；这也不代表其他接口绝不存在。

## 结论边界

已确认的是：当前账号的 41 课播放资源完整获得，最高暴露版本为 720p；这次新增的旧多云链路与上传 SDK 调查没有带来更高清可下载对象。仍未知的是：平台是否保留上传原片、原片本身分辨率，以及是否存在不在学员播放响应中提供的其他版本。现有视频没有为本次调查而替换、重编码或放大。
