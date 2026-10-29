# 配图视觉规范

目标：论文单栏、简约、少量acid元素；数据图与原结构总览共享绿黄视觉语言。

- 白底，深森林绿文字与轮廓；绿色/橄榄色承载数据，柠檬黄 `#d7e955` 用作少量强调。无彩虹色阶、阴影、立体或渐变效果。
- 统一无衬线字体、字号层级及线宽。最终宽86mm，标签至少7.5pt；正文适配最终期刊时再核对出版社要求，当前不宣称满足某个期刊的投稿规范。
- 分类计数用共同比例尺上的圆点与细参考轨迹。准确数值直接标注，保留零点；不通过粗面积夸张差异。
- 证据矩阵用实心/空心圆重复编码；空心是未编码，不能视为没有能力。所有系统均在完整矩阵出现，长名称按行分配空间。
- 页内标题和柠檬黄小编号提供识别；没有装饰性图标。
- PDF嵌入TrueType字体，线条与文字为矢量；SVG保留文字，接收方需有相应字体。PNG为400dpi白底预览，不是替代矢量源文件。
- 图中所有数值由同一份系统记录计算；不增加推断性的误差线、置信区间或能力评分。

参考：现有 `data-analytics:visualize-data` skill、[K-Dense scientific-visualization skill](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-visualization/SKILL.md) 及 [Nature图件设计与导出指南](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)。只参考其编码、可读性和矢量输出原则；保留用户指定的绿黄配色及当前栏宽。
