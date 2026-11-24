# ROAM: Bridging Vision-Language Reasoning and Learned Control for Legged Navigation in the Wild

> 📄 [论文原文](https://arxiv.org/abs/2611.25215) · 📝 [深度阅读](reading-notes.md) · 🌐 [中文翻译](translation.md)
>
> Takahiro Miki, Robin Schmid, Manthan Patel, Turcan Tuna, Julia Richter, Julian Nubert, Joonho Lee, Matthias Müller, Marco Hutter（共 9 位作者，ETH Zürich / Robotic Systems Lab 等）
> **arXiv 预印本，2026**（正文为 *Research Article* 体例，含 Materials and Methods 与 Supplementary Materials，不代表已被会议或期刊录用）
> 领域标签: #legged-navigation #VLM #sim-to-real #field-deployment #open-vocabulary
> 首次笔记: @CGmoke | 最后更新: 2026-11-24

---

## 🔗 资源链接

| 类型 | 链接 |
|------|------|
| 论文原文 | [arXiv](https://arxiv.org/abs/2611.25215) |
| PDF | [完整论文](https://arxiv.org/pdf/2611.25215) |
| 代码 | [leggedrobotics/roam](https://github.com/leggedrobotics/roam) |
| 项目主页 | [roam-hiking.github.io](https://roam-hiking.github.io) |
| 数据与影像 | [Zenodo 10.5281/zenodo.23492871](https://doi.org/10.5281/zenodo.23492871)；[Movie 1](https://youtu.be/xcqVpbgklD4)、[Zermatt 全程徒步](https://youtu.be/qaKoBthsapA)、[Seealpsee 环湖](https://youtu.be/1TAuPEN80WE) |
| 成员实现代码 | 暂无 |

---

## 🎯 一句话概括

ROAM 不让 VLM 输出坐标、路径点或电机指令，而只让它**给场景里的语义标签打三个 0–1 的分值**（risk / steppable / preferred_area）；开词汇分割把这些标签铺成稠密风险图，投影到 2.5D 高程图，再交给两条仿真训练的 RL 策略做 10–50 Hz 的运动与局部导航——于是「慢而懂常识的 VLM」与「快而抗噪的 RL」解耦，ANYmal D 四足机器人得以在瑞士阿尔卑斯完成 **10.1 km / 高差 1220 m** 的自主徒步（时间自主率 96.7%）。

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
| Zermatt 徒步 | **10.1 km** / 高差 **1220 m** / 最陡约 30% 坡度 | §2.1、图 3A；Gornergrat 站（海拔 >3000 m）→ Furi 缆车站 |
| Zermatt 时间自主率 | **96.7%** | §2.1；全程 2 次人工干预，均因施工区分割失败 |
| Seealpsee 环湖徒步 | **2.38 km** / 高差 20 m | §2.1、图 3B；含临湖窄道、牧场、牛群、树木遮挡 GNSS |
| Seealpsee 时间自主率 | **97.5%** | §2.1；3 次干预（湖边、湿滑陡坡、无法通过的转门） |
| 干预归因 | 5 次事件中 **4 次为分割错误**、1 次物理障碍、**0 次 VLM 语义错误** | 补充材料「Limitations during the hiking experiments」、fig. S7 |
| 受控赛道 | 1.2 km，对比 Field Local Planner（纯几何）与 ViNT | §2.2、图 4；含路径偏移、假人、施工标牌三类挑战 |
| 图像级路径生成（27 场景） | ROAM A\*：**Safety 0.991 / Preferred 0.868 / 到达目标 27/27** | 表 1、图 6C；对比 8 种 VLM 输出抽象 |
| 让 VLM 直出像素坐标 | Safety 0.714 / Preferred 0.398 / **仅 5/27 到达目标** | 表 1；P=0.001（Holm 校正 Wilcoxon 符号秩检验） |
| 固定标签集基线 | TartanGround IoU 0.827 → **0.665**；Sign 0.904 → **0.612** | 表 S3；证明开词汇动态标签是必要条件 |
| VLM 查询 / 分割 / 控制频率 | **每 10 s 一次 / 6 Hz / 10–50 Hz** | §1.2、§4.4；慢语义与快控制解耦 |
| 高程图 | 4 cm 分辨率，8 × 8 m 局部范围，多图层 | §4.4；elevation + risk + steppable + preferred_area |
| 定位精度（APE） | 融合 **0.44 ± 0.61 m** vs LiDAR-only 1.43 ± 1.19 m / GNSS-only 0.54 ± 0.98 m | 表 S1；Graph-MSF + 退化感知 X-ICP LiDAR SLAM |
| 硬件 | ANYmal D；6× RealSense 双目 + Velodyne LiDAR + 198° FOV C1 前置相机 + RTK GNSS + Jetson AGX Orin | §4.2；另配 4G 路由以调用云端 VLM |
| VLM | gpt-4-vision-preview（云端闭源），图像缩至 640 × 427 | §4.4；后续 benchmark 另评 gpt-4o / gemini / gemma / qwen |
| 评测规模 | 徒步与赛道**每方法 N = 1**；假人避障 N = 10；图像评测 N = 27 | §4.1、§4.9；样本量由野外时间决定，未做 power analysis |

---

## 💬 讨论与备注

- **本文最值得记的是「动作抽象层级」的取舍。** 表 1 把几种 VLM 用法放在同一张表里：输出语义标签（0.991）、输出离散标签序列、输出像素坐标（0.714 / 仅 5 次到达）、直接输出底层指令。结论不是「VLM 不够强」，而是**当前 VLM 的精确空间推理不可靠**，所以把空间推理外包给分割 + A\* + 几何规划。这与仓库里 RT-2 / OpenVLA 一类「让大模型直接出动作」的路线形成有意思的对照。
- **「自主率」是时间占比，不是任务成功率。** 10.1 km 与 2.38 km 各只跑了一次（N=1），且作者明说样本量由野外可用时间决定、未做功效分析。96.7% / 97.5% 应读作「一次长距离部署的描述性统计」，不能当可复现的成功率。
- **失败几乎全在分割，不在大模型。** 补充材料把 5 次干预逐一归因：湖岸浅水与地面视觉混淆、湿滑陡坡路径不清、施工区栅栏漏检、旧路被落石阻断而新路偏移 10–20 m 未分割出——4 次是开词汇分割错误，1 次是转门物理不可通过，0 次归因于 VLM 语义判断。这既说明架构的瓶颈位置，也是作者自陈的改进优先级。
- **系统并未完全自主。** 长距离任务仍依赖人在卫星图 GUI 上点选粗略 waypoint，由 OpenRouteService（含瑞士徒步路径）生成全局 LLA 路径；作者把「VLM 无法充分理解全局地图」列为局限。此外依赖云端闭源 VLM + 4G 网络，夜间、浓雾、暴雨、强逆光均未充分测试。
- **一个 concept-level 的坦白**：作者指出当前「常识」只建立在视觉与文本上，**无法表达薄冰 / 深泥 / 松砾石这类需要物理接触才能区分的材质差异**，高层语义与真实物理接触是脱节的（§3）。这一条恰好是本期另一篇 Force2Act 从底层补上的方向，见两篇卡片的「个人收获」。
- **读数字时留意版本迁移**：正文部署用 gpt-4-vision-preview，VLM benchmark 用 gpt-4o，prompt 消融又换成 gemini-3.5-flash——作者把它当作「模型无关」的证据，但也意味着**跨表格的绝对值不可直接横向比较**。

---

> 💡 **快速使用指南**
> - 想看「语义标签 → 风险图 → RL 策略」三段怎么接？看「深度阅读」第 2 节
> - 想看为什么不让 VLM 输出坐标？看第 3 节表 1 与第 5 节
> - 想看这系统到底哪里还会坏？看第 4 节批判性思考
