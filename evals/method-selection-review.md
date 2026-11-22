# 构建方法选型的实际调研检查

日期：2026-11-21。类型：维护者实际检索、阅读和比较的有限任务。测试问题是“为比较皮层不同层的静息发放率，如何选择构建路线”。该问题仅用于检查 Skill 的方法选择流程，不代表已确定用户模型的生物学方案。

## 检索与实际阅读

使用检索式 `Potjans Diesmann 2014 cell type specific cortical microcircuit model construction full text` 和 `Brunel 2000 dynamics sparsely connected networks excitatory inhibitory spiking neurons full text`，随后沿论文与官方实现链接核对方法。纳入以下两项原始研究及一套相关实现；同一模型的论文、文档和代码不计作三个独立模型。未把检索摘要当作已阅读的方法。

| 来源 | 实际阅读范围与版本 | 对构建路线的影响 |
| --- | --- | --- |
| P01：[Brunel 2000](https://webhome.phy.duke.edu/~nb170/pdfs/brunel00JCNS.pdf) | PDF 第 2–3 页，`The Model`：兴奋/抑制群体、随机输入连接数、LIF 动力学及外部输入。 | 可作为抽象 E/I 状态研究的候选。仅据这些定义，不能直接回答分层发放率问题。 |
| P02：[Potjans–Diesmann 预印本](https://arxiv.org/pdf/1106.5678) | 实际取得的是 2011-06-28 的 v1；阅读 PDF 第 4 页连接概率关系、第 10–12 页仿真方法与表 2、3。 | 包含四层的八个 E/I 群体及群体间连接定义，对测试问题具有更直接的结构对应。这里未声称已核对 2014 年正式发表版全部方法。 |
| C01：[官方实现说明](https://microcircuit-pd14-model.readthedocs.io/en/stable/pynest_implementation.html)及源码 | 阅读 PyNEST 实现说明，并读取下面固定版本中的三个源文件。 | 将文献中的动力学、连接数量与突触量对应到具体配置和函数；没有安装或运行 NEST。 |

源码版本为 `849185b3f989dfd5d5c693415808830221b99910`。实际定位如下：

- [network_params.py](https://github.com/INM-6/microcircuit-PD14-model/blob/849185b3f989dfd5d5c693415808830221b99910/PyNEST/src/microcircuit/network_params.py#L63)：神经元类型、八个群体、连接矩阵方向及膜时间常数配置。
- [helpers.py](https://github.com/INM-6/microcircuit-PD14-model/blob/849185b3f989dfd5d5c693415808830221b99910/PyNEST/src/microcircuit/helpers.py#L46)：连接概率到突触数，以及突触后电位到电流的转换函数。
- [network.py](https://github.com/INM-6/microcircuit-PD14-model/blob/849185b3f989dfd5d5c693415808830221b99910/PyNEST/src/microcircuit/network.py#L225)：调用转换并缩放数量；第 473–520 行将数量传入实际连接规则。

GitHub API 请求遇到限流，随后从公开目录页取得版本，再读取该版本原始源码。此次只阅读，没有下载数据、执行外部代码或验证参考输出。

## 选型决定与参数对应

对上述测试问题，优先采用 P02 的分层结构作为待检验路线，P01 保留为简化对照。这是基于输出需求与已读方法的判断，不是生物学优劣排名。进入真实构建前，仍需核对动物、脑区、实验状态、规模与数据条件；不能直接将该模型称为特定小鼠 S1 模型。

实际转换示例：C01 的 `neuron_params.tau_m` 为 `10.0 ms`；若目标实现采用秒，应登记 `10.0 × 0.001 = 0.010 s`，再检查实际神经元对象。这里没有实例化该模型，因此实际对象一栏应保持未完成，不能用配置值代填。连接数量还取决于抽样与重复接触定义，不能一律以概率乘神经元对数替代所读转换。

论文方法、当前代码版本和目标实现分开登记；本文的合成 LIF 流程测试使用工程测试参数，未采用本记录构建或复现上述论文网络。

## 本次检查的结论与范围

已实际完成检索、两种构建路线比较、代码位置核对、选型理由与参数单位转换示例。发现正式发表版与预印本的一致性仍待核对；未取得实测数据，未完成生物学参数校准，也未作独立智能体行为评测。该案例用于检查有限的方法选型流程，不能替代完整建模任务通常需要的 3–5 篇精读与按缺口追加调研。
