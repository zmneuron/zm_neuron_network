# 纳入范围、四张表与数据用途

正式论文以出版社或可信登记的首次**在线**日期归入 2016-11-26 至 2026-11-26。电子预发表优先于卷期日期。Europe PMC 的 `electronicPublicationDate`、Crossref 的 `published-online` 及期刊出版史分别注明来源。单有年份、卷期、索引时间或自动补成的一月一日，保留题名和出处，`date` 写“未核实”，另存 `reported_year`/`date_note`，暂不进入窗口计数。早期论文可注明有出处的原出版日期及其口径。预印本按版本一首次张贴日期，另存正式版本及 `preprint_of` 边。资料归入哪一组与能否自由下载分别判断。

- **窗口内的建模研究。** 含针对神经系统的理论、动力系统、概率统计、生物物理、混合、数据驱动模型及明确定义神经观测的编码与解码。只要能说明具体问题与用途，纯理论、未做新实验或未开放数据的研究均可收录基本行。
- **支持性资料。** 纳入可约束具体模型量/协议、区分预测或支持实现与复现的原始实验、数据论文、计算与数学方法、协议、图谱、基准与软件。综述和教程可列线索，具体实测注明原实验出处。单纯泛指“使用 AI”、没有神经系统测量或建模用途的资料留在候选筛选记录。
- **资源可先于论文。** 资源独立建行。优先固定版本、实验号或样本页。多份记录来自一项实验时分别说明数据形态与关系。尚未找到使用它的模型，可在 `model_use_status` 注明“本批未定位”，以后补边。结果位置只定位到图时仍可收录，数据状态保持实际层级。
- **窗口外经典来源。** 作为参数、模型或原实验的相关来源，保留与窗口内研究或资源的具体关系，单列统计。预印本、版本和更正不重复计作彼此独立的研究。

## 文件与字段

四表为 UTF-8 JSONL，每行一个 JSON 对象。稳定 ID 一经发布便保留。`tags` 为多值词表 ID，`source` 给本行事实的公开依据。可增补 `identifiers`、`age`、`layer`、`cell_type`、`study_split`、`access_note`、`license_source`、`model_use_status`、`corrects` 等有用字段。未知内容写“未报告”表示已查原出处没有报告，“未核实”表示尚未查明，“不适用”需要与对象相符。

| 表 | 必填字段与含义 | 同一条记录的识别 |
|---|---|---|
| `papers.jsonl` | `id,title,authors,doi,date,status,kinds,url,source,use,data_status,tags`。`authors` 可用首作者等，`use` 写研究问题与能帮助做什么。`kinds` 可并存 model/theory/experiment/data/method/software/review。`status` 可为 published/preprint/correction/thesis/conference。 | 规范化 DOI（去前缀、忽略大小写），无 DOI 用 PMID/arXiv/机构号和题名核验。预印本与正式版本各一行并关联。 |
| `results.jsonl` | `id,paper,locator,source,origin,species,anatomy,preparation,state,protocol,control,metric,unit,value,window,grouping,independent_unit,use,constraint,family,tags`。`locator` 精确到面板、表、补充文件、样本+试次。`value` 可为真实数值、方向或有出处的相容/失败结果。`use` 写原研究用途，`constraint` 写能映射到哪个模型量、必要转换和局限。 | 论文、图/试次、来源种类、对象、协议和指标共同决定。混合图的实验点、模拟曲线和参数反演分开并关联。按相同条件补字段不会新建结果。 |
| `resources.jsonl` | `id,kind,title,accession,version,url,source,access,license,checked,use,family,tags`。`checked` 用 ISO 日期。种类可用 raw/processed/figure_data/protocol/waveform/model_code/analysis_code/tool/atlas/parameter/format/benchmark/reproduction/portal。`raw` 可含记录设备原生或归档的原始信号，已处理谱、尖峰或示例文件的层级写清。 | 数据库及编号与具体版本为主，相同版本的别名或镜像保留共同来源。提交版本/文件编号可作代码版本。门户主页只列 portal。 |
| `links.jsonl` | `from,to,relation,detail,source`。边有方向。用实际关系说明原始采集、再次分析、定参、检验、模拟生成、资源支撑、镜像、版本更新或更正。`detail` 写配对层级或复用范围。 | 起点、终点和关系构成一条边，补充出处与说明沿用原边。只在有来源时建立“使用了此数据”的关系。 |

`origin` 中 measured_here 为对应来源本研究实测，cited_measurement 为引自其他实验，published_aggregate 为已发表的实验汇总，simulation 为模拟，inferred 为推断参数，theory 为数学推导。分类描述读数本身。拟合得到的时间常数和实际电压轨迹可以有不同来源。文献的数据状态为 linked（有明确数据记录）、not_located（已查未定位）、not_public（作者明示未公开）、unchecked（待查）或 not_applicable。代码公开本身不构成原始实测公开。

数据先行且采集论文尚未定位时，结果的 `paper` 写“未核实”，用 `resource` 指向已登记的具体数据版本或样本。查询会返回资源入口。作者或数据库汇总原始脉冲得到的特征可以归入 published_aggregate，逐行说明计算方法、来自哪个试次以及是否复算。分类器权重、连接推断和拟合参数归入 inferred。

`access` 分别表示 public 可公开获取，registration 需注册，application 需申请，not_public 明确未公开，not_located 已查未定位，broken 链接已失效，unchecked 待核实。网页可访问与其中的数据文件可取得分别记录。未能抓取、单次超时或接口限流只记当次情况，不能据此断定数据未开放。文献、图表、原始记录、代码与镜像按各自许可填写。

## 比较边界

设定拟研究对象、状态、刺激零点与对照后，核对单位、窗口、分母、分组和独立样本。将模型膜电位、模拟尖峰、场电流或群体活动按实验同一处理得到读数。荧光需相应钙动力学和指示剂/成像过程，脑磁和场电位需要电流源与测量几何，血氧需血流动力学，行为须指明动作或任务模型。形态与连接组可约束结构，单独使用时不能检验放电动力学。

`family` 表示已确认的共同来源范围。相同家族是需要追查复用的线索，家族不同也不自动保证独立。记录发表研究中的选参、选模、开发/测试划分及哪些试次、细胞、动物被保留。在未来工程登记新鲜度之前，应检查此项目此前是否使用其数值、方向、图形或协议来作选择。新噪声种子只回答模拟重复；同细胞新刺激、新细胞和新动物各自检验不同外推范围。

新增标签应在[词表](vocabulary.tsv)给出维度、中英文名称以及用分号分隔的同义词、缩写或旧称。`recording` 表示记录方式，`signal` 表示读数，`related` 表示需要转换的其他观测。同一算法的名字相似时，核对具体实现和公式。保存公开材料的事实和短说明，避免存储动物/参与者私有信息、本机路径、凭据及许可未允许重新分发的内容。

## 导入和更新

一份待提交的 UTF-8 JSON 对象可含四张表的数组，还可附 `vocabulary`、`searches`、`gaps`。各行沿用现有字段名称。检索行含 id、platform、query、url、date、years、language、scope、outcome、status。待补行写 id、status、conditions、search_ids、platforms、keywords、date、next。复查过的暂缺条件以新记录关联旧 ID，保留先前的检索范围。

导入按 DOI、PMID、arXiv 或机构标识核对文献，资源以编号与版本核对，未分配编号时用同版资源的具体 URL。结果按规范化父记录、原图/试次、来源性质、对象、协议、读数、分组与窗口核对。同源的实验和模拟可指向同一图，保留各自的行。不同数据库的镜像或图号的异写须对照原出处后补边。源记录事实有更正时，用原 ID，附 `replace_fields`、`change_note` 与 `source`。新版本另建 ID 和版本关系。需要报告资源失效时，注明核实日期、访问失败的具体层级和已经复查的替代入口。

维护者在原索引以外指定新目录生成待合并副本，先校验并复查原问题，再提交可读的差异。只有正式合并到共享仓库并复查可检索后，才将相应条目标作已入库。
