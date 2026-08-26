# fig-agent 官网

这是一个无构建依赖的静态网站，可直接部署到 Vercel Hobby。

## 本地预览

在仓库根目录运行：

```powershell
python -m http.server 4173 --directory website
```

然后访问 `http://localhost:4173/`。

## 部署

最简单的方式是在 Vercel Drop 中上传整个 `website` 目录。部署完成后，把 `fig-agent.cn` 和 `www.fig-agent.cn` 绑定到该项目。

## 产品演示

首页使用约 20 秒的真实工作流循环，覆盖多文件导入、自然语言绘图、任务确认、结果生成、OPJU 导出，以及在 OriginPro 中打开图和工作表：

- `assets/demo/plotagent-workflow.webm`
- `assets/demo/plotagent-workflow.mp4`
- `assets/demo/plotagent-workflow-poster.webp`

视频默认静音循环播放，提供暂停按钮；系统启用“减少动态效果”时仅显示封面。

## 34 图模板图库

`assets/templates/gallery/manifest.json` 记录 34 个图类的名称、Origin 官方模板和样例数据来源。每个图类都包含 PlotAgent 实际生成的两张预览：

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
