# 仓库首页的思考逻辑图

本图概括 [技能入口](../../SKILL.md) 的六步主线，不是某个神经网络的结构图，也不代替具体项目的方法图。默认有基础发放的静息态、分轮追问与结束提示、来源到参数的对应、逐题交付和按缺口返回均沿用现行规范。

点模型优先针对未指定表示的新建逐神经元网络；复现、解析、群体/场模型等已有范围继续有效。图中局部响应检查按实际主张启用，独立评价按实际取得的数据报告；图示不表示所有步骤在某个项目中已经完成。方法依据见[表示选择](../../references/method-discovery.md#点模型优先与形态需求)与[关键过程和观测](../../references/construction-methods.md#关键过程与观测约定)。

修改 [Mermaid 源码](overview.mmd) 后重新生成 [SVG](overview.svg) 和 [PNG](overview.png)，再更新首页。绘图采用 Mermaid 11.17.2 的 `handDrawn` 风格及固定绘图种子；这是手绘风格的程序图，不是人工手绘。文字保留为 SVG 文本，PNG 用于跨设备稳定展示中文。

生成脚本需要 Python、Playwright 及 Chromium 浏览器。将 [Mermaid 11.17.2 官方包](https://www.npmjs.com/package/mermaid/v/11.17.2) 中的 `dist/mermaid.min.js` 保存至本地后，从本目录运行：

```text
python -B render.py --mermaid-js <本地mermaid.min.js路径>
```

已有 Chromium 浏览器可用 `--browser <浏览器可执行文件路径>` 指定。脚本不下载或安装依赖；本仓库不附带浏览器和 Mermaid 运行库。字体按 `Microsoft YaHei`、`Noto Sans CJK SC`、系统无衬线依次选择，重绘机器需要可显示中文的字体。
