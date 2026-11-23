# 仓库首页的 Excalidraw 流程图

六个框各保留一个简短阶段：**明确问题 → 调研讨论 → 确定方案 → 构建检查 → 运行比较 → 解释交付**。虚线回路表示按结果调整；具体返回哪个环节由实际问题决定。

本图是 [技能主流程](../../SKILL.md) 的概括，详细建模要求仍以技能正文为准，不表示某个模型已经完成。

## 图件与编辑

- [Excalidraw 原始文件](overview.excalidraw)：包含可编辑的框、文字和绑定箭头。
- [SVG](overview.svg)：矢量图，嵌入所需字体与场景信息。
- [PNG](overview.png)：用于 GitHub 首页展示。

用 [Excalidraw](https://excalidraw.com) 打开或拖入 `overview.excalidraw`，即可修改文字、颜色和位置。修改后保存原始文件，并重新导出 SVG 和 PNG，更新同名文件。

本版通过 [Excalidraw 官方项目](https://github.com/excalidraw/excalidraw) 的 `@excalidraw/excalidraw` 0.18.0 创建与导出，采用手绘线条和自带中文手写字体。已检查原始场景重新载入、文字和箭头绑定，以及实际导出的图像；旧 Mermaid 源码与渲染脚本由 Git 历史保留，当前目录只维护这一版。
