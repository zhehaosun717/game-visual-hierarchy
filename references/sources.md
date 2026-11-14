# 参考资料

每条后面写的是本技能从中吸收了什么。原则性的内容都经过转述，没有照搬原文。

## 画面层级与可读性

- **Riototown，《Dev Blog: Defining the Rift's Visual Style》**，Riot Games，2014 年 11 月。官网原链接已失效，全文镜像：<http://wiki.polycount.com/wiki/Defining_the_Rift%E2%80%99s_Visual_Style>
  本技能的起点：分层与可见度顺序、每层的明度与饱和度范围、环境退后并引路、UI 窄小、隐藏技术痕迹。详见 [rift-case-study.md](rift-case-study.md)。
- **Riot Games，《Clarity in League》**，2021 年 3 月。<https://www.leagueoflegends.com/en-us/news/dev/clarity-in-league/>
  显眼程度要和玩法分量相称；能躲的东西应该更显眼；不能应对的效果做成预警的样子是一种错误的承诺。
- **Brandon "mochi" Wang，《VALORANT Shaders and Gameplay Clarity》**，Riot Games Tech Blog，2020 年 6 月。<https://www.riotgames.com/en/news/valorant-shaders-and-gameplay-clarity>
  各档画质之间不能有影响玩法读取的差异；按区域限定角色的明暗范围。
- **Jason Mitchell，《Stylization with a Purpose: The Illustrative World of Team Fortress 2》**，Valve，GDC 2008。<https://cdn.fastly.steamstatic.com/apps/valve/2008/GDC2008_StylizationWithAPurpose_TF2.pdf>
  剪影要读得出角色身份、朝向和武器；最高的对比留给承载玩法信息的部位。
- **Valve，《Dota 2 Workshop – Character Art Guide》**。<https://help.steampowered.com/en/faqs/view/0688-7692-4D5A-1935>
  角色内部的明度和饱和度分配；低细节的"休息区"。

## 无障碍与安全

- **W3C，《Understanding WCAG 2.2 Success Criterion 2.3.1: Three Flashes or Below Threshold》**。<https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html>
  闪光的定义、每秒三次的上限、相对亮度的定义。
- **ITU-R BT.1702-3，《Guidance for the reduction of photosensitive epileptic seizures caused by television》**，2023 年 11 月。<https://www.itu.int/rec/R-REC-BT.1702/en>
  电视口径的闪光面积与间隔。
- **Microsoft，Xbox Accessibility Guidelines 118: Photosensitivity**。<https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/118>
- **Microsoft，Xbox Accessibility Guidelines 102: Contrast**。<https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/102>
  关键玩法元素对最不利背景的对比度下限（3:1 与 4.5:1）；描边要在所有背景上成立。
- **Game Accessibility Guidelines，《Avoid flickering images and repetitive patterns》**。<https://gameaccessibilityguidelines.com/avoid-flickering-images-and-repetitive-patterns/>
- **Electronic Arts，IRIS**（开源的闪光检测工具）。<https://github.com/electronicarts/IRIS>

## 色彩科学

- **CIE 1976 L\*a\*b\***（CIELAB）：脚本里的感知明度 L* 和色度 C*。
- **IEC 61966-2-1:1999**（sRGB）：码值到线性光的换算。
- **Machado、Oliveira、Fernandes，《A Physiologically-based Model for Simulation of Color Vision Deficiency》**，IEEE TVCG 15(6)，2009：脚本里红色盲、绿色盲模拟所用的矩阵。

## 声明

本技能是独立整理的实践指南，与 Riot Games、Valve、Microsoft 等上述机构没有关联，也未获其认可。League of Legends 等名称是各自所有者的商标。技能里不包含上述资料的原图或成段原文。
