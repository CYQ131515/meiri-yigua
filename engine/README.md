# 运势计算引擎

历法、四柱、黄历、西方占星与每日报告生成，只依赖 Python 标准库。

这部分代码原先属于作者的「自动化任务」项目，现在随「每日一卦」一起内置并以 MIT 发布。
天文算法参考 Meeus《Astronomical Algorithms》、VSOP87D 截断数据等公开资料，
具体依据见各模块文件头注释。

```
calendar_cn.py   农历、节气、朔望、VSOP87D
bazi.py          四柱、十神、旺衰
almanac.py       黄历宜忌、值宿、建除
astro.py         行星黄经、宫位、相位
report.py        汇总为每日报告
constants.py     干支/五行/星座等常量
data/            VSOP87D 截断数据
```
