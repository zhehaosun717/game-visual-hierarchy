# game-visual-hierarchy

游戏画面视觉层级：一份 Agent Skill，教 AI 助手审查和规划"玩家能不能看清该看的东西"。

*An Agent Skill for game-frame readability. It teaches an AI assistant to decide which information must win the player's attention, and to allocate brightness, saturation, hue, detail, area, motion and timing so that terrain and decoration cannot compete with characters, threats, effects and HUD. Works for any genre, 2D, 3D, pixel art and tiny LED displays. The skill text is in Chinese; the two bundled scripts are documented in English (`-h`).*

## 它解决什么问题

- 截图看起来太乱、太花，角色融进背景，玩家看不清路、敌人、攻击或提示；
- 特效已经很亮了，玩家还是说看不见前摇；
- 要给环境美术、特效美术定一份配色和层级规范；
- 一轮美术迭代之后，想知道画面是变清楚了还是变乱了；
- 给像素图、有限调色板或 32×32 的 LED 点阵屏分配颜色。

## 核心想法

1. 画面上任何"显眼"——更亮、更暗、更艳、更密、更大、在动——都花在同一份注意力预算上。
2. 做层级的关键是**约束下层**，而不是拔高上层：给最底层的画布划一个窄的范围，把上层要用的方向空出来。
3. 最强的通道留给玩家最需要读到的信号，做成只归它的专属档，玩家才学得会。
4. 修问题的顺序：先把越界的下层收回去，再考虑换通道，最后才加强上层。

方法的起点是 Riot Games 2014 年的开发者博客《Defining the Rift's Visual Style》，并结合了其他公开资料和实测做了扩展。哪些是原文的主张、哪些是本技能的推论，见 [references/rift-case-study.md](references/rift-case-study.md)。

## 安装

本仓库的根目录就是技能目录。把它放进你所用工具的技能文件夹即可。

Claude Code：

```bash
git clone https://github.com/zhehaosun717/game-visual-hierarchy ~/.claude/skills/game-visual-hierarchy
```

其他支持 Agent Skills（`SKILL.md`）格式的工具，克隆到它自己的技能目录。

两个脚本需要 Python 3.9 以上，以及 Pillow 和 numpy：

```bash
pip install pillow numpy
```

## 怎么用

安装后直接用自然语言提问，例如：

- "帮我看看这张截图，机器人在废料堆里是不是太难找了？"
- "给我的像素塔防定一份配色规范，后期满屏的时候也不能乱。"
- "Boss 的前摇玩家总说看不见，可能是哪里的问题？"

也可以单独使用脚本。

按层测量一张截图（层从底到顶列出，`!` 表示"其余全部"）：

```bash
python scripts/sv_profile.py shot.png -o out -r "!environment:0,0,1,1" -r "player:0.42,0.40,0.50,0.55" -r "hud:0,0.88,1,1"
```

比较同机位的前后两帧：

```bash
python scripts/sv_profile.py after.png -o out -r "!world:0,0,1,1" --baseline before.png
```

分析一段 LED 动画（线性驱动的面板）：

```bash
python scripts/sv_profile.py anim.gif -o out --frame all --display-gamma 1 -r "!bg:0,0,1,1"
```

在动笔之前检查分层调色板：

```bash
python scripts/palette_check.py palette.txt -o swatches.png --reserve "V>=90:fx" --reserve "H=330-20&S>=60:enemy"
```

完整参数见 `-h`。Windows 上如果 `python` 不可用，换成 `py`。

`sv_profile.py` 会报告每一层的面积、饱和度与明度范围、感知明度（L\*）、细节密度、专属档归属、和周围画布的局部对比，并输出灰度图、模糊图、最亮档分布图，以及红色盲、绿色盲的模拟图。

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 技能正文：原则、分配规则、检查方法、输出格式 |
| `references/layer-stacks.md` | 13 种游戏类型的分层起点与典型的崩溃方式 |
| `references/limited-palette.md` | 像素图、有限调色板、LED 点阵与小屏 |
| `references/3d-lighting.md` | 3D、写实与动态光照 |
| `references/evidence-and-measurement.md` | 怎样核对截图、取样、读测量结果；闪光安全 |
| `references/rift-case-study.md` | 原文的主张、图表与真实画面的实测、局限 |
| `references/sources.md` | 参考资料 |
| `scripts/sv_profile.py` | 按层测量截图 |
| `scripts/palette_check.py` | 检查分层调色板 |
| `scripts/test_scripts.py` | 两个脚本的回归测试 |
| `evals/` | 修改技能后用来复测的任务和触发用例 |

运行测试：

```bash
python scripts/test_scripts.py
```

## 参考资料

- Riototown，《Dev Blog: Defining the Rift's Visual Style》，Riot Games，2014
- Riot Games，《Clarity in League》，2021
- Brandon "mochi" Wang，《VALORANT Shaders and Gameplay Clarity》，Riot Games Tech Blog，2020
- Jason Mitchell，《Stylization with a Purpose: The Illustrative World of Team Fortress 2》，Valve，GDC 2008
- Valve，《Dota 2 Workshop – Character Art Guide》
- W3C，WCAG 2.2 成功准则 2.3.1（闪光）；ITU-R BT.1702-3
- Microsoft，Xbox Accessibility Guidelines 102（对比度）与 118（光敏）
- Machado、Oliveira、Fernandes，色觉缺陷模拟模型，IEEE TVCG，2009

链接和每条资料的用途见 [references/sources.md](references/sources.md)。

## 声明

这是独立整理的实践指南，与 Riot Games、Valve、Microsoft 等机构没有关联，也未获其认可。League of Legends 等名称是各自所有者的商标。仓库里不包含上述资料的原图或成段原文。

技能里的数值都是起步值或某个案例的测量结果，不是标准。请用你自己项目的画面去验证。

## 作者与许可

作者：Imanus（[@zhehaosun717](https://github.com/zhehaosun717)）

以 [MIT 许可](LICENSE)发布。
