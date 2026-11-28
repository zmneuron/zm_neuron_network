# 参数与实际网络的自动核对

原清单详细事项、启用模块七项定义及完成状态，另按[逐项完整性检查](element-coverage.md)核对；本页数值工具通过不能代替模块完整性检查。

[check_model.py](../scripts/check_model.py) 只读取指定文件，默认向标准输出打印 JSON，失败返回非零退出码。可检查参数对应、有限种类的单位转换和导出的细胞/连接 CSV。不会执行来源公式、导入模型或自动调参，也不会修改配置、数据和源码。它不能判断文献适用性、机制是否正确或是否得到实测验证。

## 参数表与实际配置

从[参数表表头](../assets/parameter_mapping.csv)开始，补充本次研究的行。保持一份主要参数对应表。自动核对需要 CSV；已有 Markdown 表可以继续人工核对，明确未执行自动工具，不宣称二者等价。配置使用本次解析完所有覆盖值后的 JSON；已有后端采用其他格式时，由本项目读取器导出对应 JSON，不能手写一份与运行无关的配置。

每个参数以 `parameter_id` 标识，`config_path` 使用 JSON pointer 路径，如 `/cells/E/tau_ms`、`/probability/0/1`。路径中的 `/` 和 `~` 按 JSON pointer 分别写成 `~1` 和 `~0`。数组或矩阵可在一行表示，形状和全部数值一并比较；行列语义仍要在构建方法中说明。

| 字段 | 工具中的含义 |
|---|---|
| `parameter_id, config_path` | 唯一参数标识与实际配置路径。重复标识、路径、缺失值或未覆盖的数值配置项都报错；布尔开关和字符串如需核对可另列。 |
| `source_ref, source_value, source_unit` | 来源定位与原值。值使用 JSON 标量或数组；来源真实性、原文定位与适用条件需要研究者和 AI 根据原始材料核对。 |
| `method` | `direct` 原值原单位采用；`unit_conversion` 有限种类单位换算；`derived` 推导；`fitted` 拟合；`assumption` 建模假设；`numerical_setting` 数值或运行设置。 |
| `model_value, model_unit` | 本模型采用值与明确单位。默认相对容差 `1e-9`、绝对容差 `0`，可逐行填写非负有限的 `rtol, atol`。容差应服务于数值表示，不能掩盖单位错误。 |
| 配置中的单位 | 对同一对象明确写有受支持 `unit` 的 `value/lower/upper/bounds`，复核参数表的量纲与倍率。参数或其直接父键含物理单位、参数表却填 `1` 时，列入人工复核。以方程和实际接口查明嵌套投射权重及电流增量的含义。 |
| `derivation_ref` | 推导与拟合必须指向项目内真实存在的计算或说明文件，可带 `#` 定位。单独检查对应表时仅核对文件并列入 `manual_review`；另提供 `--runtime` 推导记录可复算下面支持的运算，其他公式、拟合与来源适用性仍需专门检查。 |
| `code_ref, rationale` | 实际代码文件及可选 `#函数`，和采用理由。工具检查文件存在，不声称已验证函数语义。只写方案而未实现时，不运行此实施检查。 |
| `lower_bound, upper_bound, integer` | 可选的逐元素范围和整数约束。概率可设 0–1，数量可设非负整数；实际限制由本模型定义，不靠字段名称猜测。 |

表中的 `element_id, target, source_context` 等科学说明继续按构建规范填写。数值/单位在配置和对应表中出现是为了比较，更新时同步维护；实际运行配置副本作为原始记录保留。

在参数对应表中，只有 `unit_conversion` 通过单位表计算预期值。`direct` 核对原值与相同的单位标签。`assumption` 和 `numerical_setting` 核对声明值与配置。`derived` 和 `fitted` 另外核对推导或拟合文件并列入人工复核。这些方法均可登记模型实际使用的单位。参数未登记造成的覆盖缺项和单位换算失败，在报告中分别查看 `coverage` 的字段和 `parameter` 的具体原因。

支持的基本单位包括时间 `s, ms, us`、长度 `m, cm, mm, um`、角度 `rad, deg, °`、频率 `Hz, kHz` 及电生理量 `V/mV/uV`、`A/nA/pA`、`S/uS/nS/pS`、`F/uF/nF/pF`。微前缀可以写作 `u`、`µ` 或 `μ`。无量纲用 `1`，细胞或接触数量用 `count`。上述长度或角度除以时间可组成线速度和角速度单位，例如 `40 cm/s = 0.4 m/s` 与 `180 deg/s = π rad/s`。倒数时间可写作 `1/ms`、`ms^-1` 或 `ms⁻¹`，例如 `0.02/ms = 20 Hz`（表中填 `0.02` 和 `1/ms`）。

工具同时核对量纲和物理量种类。电压与电导的量纲不同，因此 `mV → uS` 会报错。弧度在国际单位制中的量纲为一，周期频率与角频率仍代表不同的物理量，因此 `Hz → rad/s` 也会报错。如需由周期频率计算相位的角频率，应以 `derived` 记录 `ω = 2πf` 及其适用条件。其他复合单位和 PSP 到后端权重等模型相关换算，应保留实际单位，由项目计算并复核。

示例命令中的 `<skill_dir>` 替换为本 Skill 所在目录，`<project>` 为模型工程：

```text
python <skill_dir>/scripts/check_model.py --project <project> --config results/<run_id>/config_used.json --parameters docs/research/parameter_mapping.csv
```

该命令不含网络检查。报告明确给出已检查参数、数值覆盖和网络检查状态；`passed` 仅表示所列检查通过，`manual_review` 不是自动通过的科学结论。空表、无效配置和无法读取的文件不能产生通过结果。

## 从实际导出表核对网络

增加 `--network tests/construction_checks.json` 指定检查说明。其作用是把本项目的配置路径与实际导出表对应，不另外抄写一套期望数值。所有文件路径相对于 `--project`；代码位置中的 `#` 后缀不参与路径解析。

下面演示检查说明的结构，其中 E、I 和配置路径要按真实项目填写，不提供默认生理参数。网络各参数路径必须已在参数表中登记。检查配置应保存在工程中，以便知道实际检查了哪些性质。

```json
{
  "cells": {
    "path": "results/run_01/raw/cells.csv",
    "populations": {"E": "/populations/E/n", "I": "/populations/I/n"},
    "coordinate_unit": "um",
    "coordinate_bounds": {"x": "/geometry/x", "y": "/geometry/y", "z": "/geometry/z"}
  },
  "connections": {
    "path": "results/run_01/raw/connections.csv",
    "weight_unit": "nS",
    "delay_unit": "ms",
    "allow_self": false,
    "allow_multiple": false,
    "projections": {
      "E_to_I": {"source": "E", "target": "I", "weight_path": "/synapses/E_to_I/weight", "delay_path": "/synapses/E_to_I/delay"}
    }
  }
}
```

- 细胞表字段是 `cell_id,population`，空间模型再包含 `x,y,z`。检查唯一标识、群体实际数量、三轴范围与有限值；非空间模型省略 `coordinate_bounds`，报告明确不检查坐标。已有别的列名时由项目导出器生成适配表，不直接重命名原始记录来猜单位。
- 连接表字段是 `source_id,target_id,projection,weight,delay`，每行代表一个实际接触。检查目标是否存在、实际来源/目标群是否符合投射定义、自连和重复对、权重及非负延迟。多接触允许与否必须显式设定，多个受体共用同一细胞对的表示也需按本模型定义处理。
- 定值用 `weight_path/delay_path`；分布的取值边界用 `weight_bounds_path/delay_bounds_path`，配置值为 `[下限, 上限]`。每个量只能选择一种。工具不据有限样本验证分布形状、连接概率、入出度或距离规则，这些属于项目自己的统计或生成规则检查。
- 数值比较会按参数表声明的单位转换到导出表声明的单位。单位声明是否符合真正写出的物理量仍需从生成代码核对；一组伪造但相互一致的表不会因本工具通过就变成可信模型。
- CSV 工具适合可导出规模的网络。大规模 HDF5、程序化连接或多区室专用格式保留原格式，由项目实现等价检查并明确覆盖范围。不得用少量抽样替代全体数量和标识检查。

```text
python <skill_dir>/scripts/check_model.py --project <project> --config results/<run_id>/config_used.json --parameters docs/research/parameter_mapping.csv --network tests/construction_checks.json --output results/<run_id>/construction_check.json
```

`--output` 必须指向尚不存在的文件，父目录须已存在，已有文件不会被覆盖。不加该参数时不写文件。项目交付时若依赖这个工具，将实际使用的脚本及 `check_records.py` 保存到项目 `tests/` 并记录版本；运行不能依赖个人的 Skill 安装路径。

## 从实际实例读取参数与复算转换

增加 `--runtime results/<run_id>/runtime.json`。导出器在对象创建后读取真实属性，保存 `parameter_id,config_path,object_ids,values,unit,getter_ref`；不能从配置重新抄出一份取值充当实例。`getter_ref` 指向实际读取属性的代码，必须包含在本次代码记录中。统一取值的参数可按全部相关对象导出；用 `count_path` 引用配置中的对象数以核对覆盖，没有该字段时工具明确留下对象覆盖待核对项。

运行导出根对象含 `schema_version: 1`、`run_id`、实际配置的 `config_sha256`、模型及导出代码的 `code_sha256`、本次 `check_ref`，以及 `parameters` 数组。检查记录格式见[联合检查说明](project-checks.md)。工具确认对象标识唯一、数量相符、单位转换后实例值等于实际配置，并验证运行、配置和代码对应。适用于逐对象同一参数设定；分布采样、按区室变化或复杂数组由项目实现对应的分布/覆盖检查，不把分布强制当成常数。

可在 `derivations` 保存关键算术推导：`parameter_id,operation,operands,result_unit`。每个操作数包含 `value,unit,source_ref`。支持 `product`、`sum` 和两个操作数的 `ratio`，重算结果再与对应配置比较；例如数量来自密度与体积。工具复算算术，不自动证明复合单位或来源适用性。生理模型相关的非线性换算仍由项目的实际函数和结构化检查核对，通用工具不执行公式字符串或任意来源代码。

联合任务中提前登记 `runtime_parameter_ids`，确保关键实例参数不能在交付时漏掉。当前适配从实际使用的后端开始：记录它的对象读取接口、后端量纲、标识、读取时机及所需规模，不预先建立覆盖所有后端的框架。维护时用真实构造并积分的合成 LIF 对象验证这条路径；这不代表已验证 NEURON/NEST 等所有后端或真实生理参数。
