# 示例：合成演示地图

## 生成地图
python examples/make_synthetic_map.py

生成 examples/synthetic_demo/map.png (1600x1100)，刻意包含：
- 白色道路网（正交 + 斜路 + 曲线路）
- 12 处地名文字（考验去文字）
- 模拟地图自带的搜索框与工具栏（考验裁切）
- 河道、绿地、建筑块

不含任何真实地点信息。

## 运行提取
python road_from_map.py --image examples/synthetic_demo/map.png --out examples/synthetic_demo/out --crop "40,100,1560,1000"

## 结果
- 寻路网格 108x64，2091 个道路格
- 路网 JSON 约 3 KB
- 地名文字与搜索框已自动剔除，路网与白色路面完全重合

## 为什么要先画描边再画路面

生成脚本里所有道路的深色描边先画完，再统一铺白色路面。

如果按「一条路画完描边和路面，再画下一条」的顺序，后画道路的描边
会覆盖先画道路的路面，人为制造出断链 —— 本示例脚本第一版就踩了这个坑，
导致路网被切成 81 个孤立块。
