# Force2Act: A Force-Aware Visuomotor Policy for Generalizable Compliant Robot Manipulation

> 📄 [论文原文](https://arxiv.org/abs/2611.29208) · 📝 [深度阅读](reading-notes.md) · 🌐 [中文翻译](translation.md)
>
> Keerthi Vasan Murugan, Fangguo Zhao, Jiafei Duan（National University of Singapore / Zhejiang University）
> **arXiv 预印本，2026**
> 领域标签: #force-aware #contact-rich #hybrid-force-position #visuomotor-policy #interaction-generalization
> 首次笔记: @CGmoke | 最后更新: 2026-11-24

---

## 🔗 资源链接

| 类型 | 链接 |
|------|------|
| 论文原文 | [arXiv](https://arxiv.org/abs/2611.29208) |
| PDF | [完整论文](https://arxiv.org/pdf/2611.29208) |
| 代码 | [MAGICLAB-NUS/Force2Act](https://github.com/MAGICLAB-NUS/Force2Act) |
| 项目主页 | [magiclab-nus.github.io/Force2Act](https://magiclab-nus.github.io/Force2Act) |
| 模型与数据 | [Force2Act-Sim](https://huggingface.co/NUSMAGIC/Force2Act-Sim)、[Force2Act-Bench-Data](https://huggingface.co/datasets/NUSMAGIC/Force2Act-Bench-Data) |
| 成员实现代码 | 暂无 |

---

## 🎯 一句话概括

Force2Act 把接触丰富的操作拆成「规划交互」与「调节交互」两层：**全局力策略**每个 action chunk 用 flow-matching DiT 预测位姿与**相对力**（按最近实测力归一化，故所规划的力随负载自动放大）；**MoFE 反应式柔顺策略**则在每个控制步用库仑摩擦导出的 7 个「力专家」（黏着 / 滑动 / 推压 / 插入）配合几何门控与路由器实时设定法向力，让接触在 chunk 内发生变化时仍保持住——真机四任务平均成功率 **94.2%**，而基线最高仅 **27.5%**。

---

## 📑 内容导航

| 模块 | 说明 | 文件 |
|------|------|------|
| 📝 深度阅读 | 方法拆解、实验数据、批判与个人收获 | [reading-notes.md](reading-notes.md) |
| 🌐 论文翻译 | 摘要、正文、结论与附录要点中文译稿（不含参考文献与图片） | [translation.md](translation.md) |

---

## 📊 关键数据速览

以下均为论文报告值，**未自行复现**；备注列标注来源章节或图/表号。

| 指标 | 数值 | 来源与说明 |
|------|------|------|
| 仿真总体成功率（305 次试验） | **93.8%** vs 最强基线 ACP 77.0% | 表 2；Force2Act-Bench 五任务加权 |
| 真机平均成功率（120 次试验） | **94.2%** vs ACP 26.7% / ForceVLA 22.5% / ManiFlow 27.5% | 表 6；Flexiv Enlight L 臂，每条件 20 次 |
| 积木翻转（Block pivoting），仿真 | 93.3% vs ACP 64.0%，其余 5 个基线全部 **0.0%** | 表 2、表 10；六种质量 0.4–0.9 kg |
| 积木翻转，按质量 | Force2Act 100 / 96 / 92 / 92 / 88 / 92%；ACP 96 / 96 / 96 / 76 / **20 / 0%** | 表 10；ACP 随负载变重而崩，本文几乎不降 |
| 压推箱子（Press-push box） | **100%**（0° / 2° / 4° 全通过）vs ACP 100 / 40 / 10% | 表 11；示教只在平面支撑上采集 |
| 真机 OOD：翻转 0.418 kg 积木 | **20/20** vs ACP 3/20 / ForceVLA 0/20 / ManiFlow 0/20 | 表 6；示教块仅 0.116 kg（约 3.6 倍质量外推） |
| 真机 OOD：10° 斜面压推 | **20/20** vs ACP 1/20 / ForceVLA 0/20 / ManiFlow 17/20 | 表 6 |
| 失败模式（积木翻转 150 次） | 总失败 **10** 次、接触丢失 **22%** / 每次 0.29 次 | 表 4；全局-only 30 次 / 59% / 1.97，MoFE-only 93 次 / 67% / 1.01 |
| 相对力表示消融 | 全局-only 相对力 86.9% vs 绝对力 **56.7%** | 表 3；绝对力回归只能复现示教量级 |
| 权重 w 消融 | w=0 全局 86.9%，w=1 仅 MoFE 67.9%，**w=0.8 达 93.8%**，0.4–0.9 稳定 | 表 3；两层缺一不可 |
| MoFE 组件消融 | 无几何门控 **48.5%**、路由器看力方向 78.4%、每类单专家 78.0%、无 level penalty 80.0% | 表 5；完整 93.8% |
| 学到的力律 | 黏着 $F_n=5.80F_t+1.19$ 与 $7.51F_t+1.97$；滑动 $\{5.99,9.35,16.14\}$ N；插入 $F_n=1.55F_\perp+7.73$ | 表 15；由 30,968 个接触帧联合拟合，无接触类型标注 |
| 实测接触力随负载 | 0.4→0.9 kg：**25.6 → 34.3 N**；压推 0°/2°/4°：**7.9 / 10.8 / 15.0 N** | 表 14、附录 7；直接证据表明力确实跟着负载走 |
| 数据规模 | 290 条力反馈遥操作示教；30,968 接触帧；305 次仿真 + 120 次真机试验 | 表 7、表 8 |
| 控制 / 规划频率 | 控制 15 Hz；chunk H=16、执行 Ha=8（0.53 s）；力专家每步调节 | §3.1、§3.2、表 8 |

---

## 💬 讨论与备注

- **「感知力」与「调节力」是两回事，这是全文的题眼。** 论文把已有工作分成三组：力只作观测/辅助目标（ForceVLA、TA-VLA、ForceFlow）、快慢双时序（RDP、ImplicitRDP、FAVLA）、显式力/刚度控制（ACP、CompVLA、Force Policy）。表 2 里 ForceVLA 观测了力却从不命令力，积木翻转仍是 0.0%；ACP 会命令刚度，但学到的是「示教里的刚度」，负载一变就退化（0.9 kg 时 0%）。Force2Act 的新意是**让被命令的力成为实测负载的函数**。
- **相对力表示是全篇最省事也最关键的一招。** 把输入 wrench 与输出 wrench 同除以 $s_t=\max(\frac1n\sum\|f_k\|, s_{\min})$，策略只需决定「力的方向与时机」，量级由测量值重新标定。表 3 里同样的架构换成绝对力回归，全局-only 从 86.9% 掉到 56.7%。这是「用归一化把 OOD 外推变成 in-distribution」的漂亮例子。
- **MoFE 的本质是把物理先验写成可学习的分段线性律。** 每个专家只有斜率 $c_j$ 与偏置 $b_j$ 两个参数，形式由库仑摩擦 $F_t\le\mu F_n$ 的四种接触情形固定；几何门控负责排除不成立的专家，路由器只从图像 + 最近 8 步「切向力 / 速度」历史里选。**路由器刻意不看机器人自己命令的法向力**——否则它会因为「当前压得轻」而选择低力专家，把力锁死在低值（表 5 验证：去掉这个约束后 0.9 kg 全灭）。
- **消融设计得很干净。** 表 4 把失败拆成 fell back / stalled / no tip 三类并统计接触丢失，直接说明「全局-only 在 chunk 内欠压导致积木倒回、MoFE-only 不知道何时该加压导致停滞」，两者互补而非冗余。表 14 更给出中位接触力随质量/斜率的实测增长，而不是只报成功率。
- **读数字时的三点折扣**：① 唯一失手的任务是 USB 插入（76.0% vs ACP / ForceVLA 96.0%）——1 mm 公差由侧向对齐而非法向力主导，力调节帮不上忙，论文如实列出；② 全局力策略是**按任务分别训练**的，MoFE 才跨任务共享，因此「generalizable」指**同一任务内的交互条件外推**，不是跨任务/跨物体的通用策略；③ 全部为刚性接触、单一法向力方向，多方向/旋转柔顺与软体接触被明确列为未来工作。
- **与本期 ROAM 的呼应**：ROAM 在讨论里坦承 VLM 的「常识」只来自视觉与文本，无法区分薄冰、深泥、松砾石，高层语义与物理接触脱节。Force2Act 正是从底层回答「如何让力反馈真正进入闭环」。两篇合起来看，恰好是「高层语义推理」与「低层物理交互」各自补上对方缺的一块。

---

> 💡 **快速使用指南**
> - 想搞懂相对力为什么能外推？看「深度阅读」第 2 节（1）
> - 想看 7 个力专家与几何门控怎么选？看第 2 节（2）
> - 想看消融怎么证明两层缺一不可？看第 3、4 节
