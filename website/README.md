# fig-agent 官网

这是一个以静态页面为主的网站；测试反馈通过 Vercel Function 写入私有 Vercel Blob。

## 本地预览

安装网站依赖后，在 `website` 目录运行：

```powershell
pnpm install --ignore-workspace
vercel dev --listen 4173
```

然后访问 `http://localhost:4173/`。只检查静态页面时仍可使用 Python HTTP Server，但反馈接口不会工作。

## 部署

在 `website` 目录运行 `vercel --prod`。部署完成后，把 `fig-agent.cn` 和 `www.fig-agent.cn` 绑定到该项目。

## 测试反馈

- 页面：`/feedback/`
- 接口：`/api/feedback`
- 私有存储：Vercel Blob `fig-agent-feedback`，香港区域
- 数据路径：`feedback/YYYY-MM-DD/<feedback-id>.json`

表单只接收问题类型、发生环节、环境版本、描述、复现步骤、诊断 ID 和可选联系方式，不接收文件或运行日志。API 会限制字段与长度，并拒绝疑似 API Key、密码或凭据。

在 Vercel 项目的 Storage 页面打开 `fig-agent-feedback` 即可查看反馈。问题处理完成后删除记录，任何记录最长保留 180 天。

## 产品演示

首页使用真实界面素材组成三幕循环：自然语言输入特写、fig-agent 绘图结果、Origin 原生结果。

- `assets/demo/plotagent-input-context.png`
- `assets/demo/plotagent-input-focus.png`
- `assets/demo/plotagent-agent-result.png`
- `assets/demo/plotagent-origin-result.png`

三幕通过 CSS 淡化转场循环播放；系统启用“减少动态效果”时仅显示第一幕。

## 34 图模板图库

`assets/templates/gallery/manifest.json` 记录 34 个图类的名称、Origin 官方模板和样例数据来源。每个图类都包含 fig-agent 实际生成的两张预览：

- `<图类 ID>-origin.webp`
- `<图类 ID>-matplotlib.webp`

首页默认显示 Origin 版本，可一键切换全部卡片；点击任意图类可并排比较 Origin 与 Matplotlib 输出。

重新生成或发布图库素材时，使用仓库根目录的两个脚本：

- `scripts/build_website_template_gallery.py`
- `scripts/publish_website_template_gallery.py`

生成脚本默认从 `D:\origin\Samples` 读取 Origin 2024 样例；安装位置不同时，先设置 `PLOTAGENT_ORIGIN_SAMPLES`。

发布脚本会拒绝缺失或失败的 Origin 结果，避免把未通过原生重开验证的图片放进官网。

## 安装包发布后

1. 把安装包上传到腾讯云香港 COS 的 `releases/<version>/` 路径。
2. 同时上传 `SHA256SUMS.txt` 和签名后的 release manifest。
3. 将 `/download/index.html` 的状态文案替换为版本信息和正式下载链接。
4. 正式下载按钮仍先进入 `/download/`，该页面访问量可作为“下载发起次数”。
5. Vercel Hobby 只保留最近一个月普通页面访问统计；需要长期或文件级统计时再启用 COS 日志方案。

安装包未发布前，不要放置不存在的下载 URL。
