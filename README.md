# PlotAgent

面向通用科研用户的对话式绘图 Agent。用户上传数据并明确选择图形，Agent 生成结果、接受自然语言修改，并导出 PNG、SVG 和 Origin `.opju` 文件。

## 本地环境

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

`originpro` Python 包已列为核心依赖，但生成 `.opju` 时仍需要 Windows 环境中安装并授权可用的 Origin。
