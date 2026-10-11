"""
生成一张合成演示地图，用于开源示例。

刻意包含：白色道路网、地名文字、搜索框 UI、河道、建筑块 —— 覆盖提取器的各个考验点。
不含任何真实地点信息。

绘图要点：先把所有道路的深色描边画完，再统一铺白色路面。
若按「一条路画完再画下一条」的顺序，后画道路的描边会切断先画道路的路面，
人为制造出断链（这正是本脚本踩过的坑）。
"""
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1100
BG = (232, 240, 245)
ROAD = (255, 255, 255)
ROAD_EDGE = (205, 215, 222)
WATER = (170, 215, 240)
GREEN = (222, 238, 222)
BUILDING = (226, 231, 236)
TEXT = (60, 70, 80)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# 绿地
d.rounded_rectangle([80, 130, 380, 340], 12, fill=GREEN)
d.rounded_rectangle([1180, 640, 1500, 900], 12, fill=GREEN)

# 河道（斜穿）
d.line([(880, 0), (830, 340), (900, 620), (960, H)], fill=WATER, width=46)

# 建筑块
for x, y, w, h in [(430, 250, 120, 80), (640, 250, 130, 80), (430, 430, 120, 90),
                   (640, 430, 130, 90), (430, 640, 120, 90), (640, 640, 130, 90),
                   (1080, 250, 140, 90), (1080, 430, 140, 90),
                   (200, 640, 150, 100), (200, 830, 150, 90)]:
    d.rounded_rectangle([x, y, x + w, y + h], 8, fill=BUILDING)

# ---- 道路定义 ----
roads = [
    # 横向主干道
    ([(60, 200), (1540, 200)], 16),
    ([(60, 390), (1540, 390)], 13),
    ([(60, 600), (1540, 600)], 13),
    ([(60, 790), (1540, 790)], 16),
    ([(60, 960), (1540, 960)], 18),
    # 纵向道路（上下都延伸过横向路，确保交叉连通）
    ([(160, 190), (160, 975)], 13),
    ([(390, 190), (390, 975)], 13),
    ([(610, 190), (610, 975)], 13),
    ([(800, 190), (800, 975)], 13),
    ([(1040, 190), (1040, 975)], 13),
    ([(1260, 190), (1260, 975)], 13),
    ([(1440, 190), (1440, 975)], 13),
    # 斜路与曲线路（考验非正交道路）
    ([(390, 600), (610, 390)], 11),
    ([(1040, 600), (1160, 700), (1260, 790), (1420, 880)], 11),
]

# 第一遍：所有道路的深色描边
for pts, w in roads:
    d.line(pts, fill=ROAD_EDGE, width=w + 4, joint="curve")
# 第二遍：统一铺白色路面（保证交叉口全部连通）
for pts, w in roads:
    d.line(pts, fill=ROAD, width=w, joint="curve")

# ---- 地名文字（考验去文字）----
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
    small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
except Exception:
    font = ImageFont.load_default()
    small = font

labels = [
    ("一号教学楼", (455, 290), font),
    ("二号教学楼", (665, 290), font),
    ("三号教学楼", (665, 470), font),
    ("图书馆", (1100, 290), font),
    ("实验楼", (1105, 470), font),
    ("学生公寓", (215, 680), font),
    ("体育馆", (215, 865), font),
    ("运动场", (1210, 680), font),
    ("东门", (1450, 940), small),
    ("西门", (105, 940), small),
    ("北门", (820, 165), small),
    ("景观河", (955, 500), small),
]
for text, pos, f in labels:
    d.text(pos, text, fill=TEXT, font=f)

# ---- 模拟地图自带搜索框 UI（考验裁切）----
d.rounded_rectangle([30, 20, 420, 70], 8, fill=(255, 255, 255))
d.text((48, 33), "搜地点、查公交、找路线", fill=(150, 158, 165), font=small)
d.rounded_rectangle([1330, 20, 1560, 66], 6, fill=(255, 255, 255))

os.makedirs("examples/synthetic_demo", exist_ok=True)
img.save("examples/synthetic_demo/map.png")
print("已生成 examples/synthetic_demo/map.png  1600x1100")
print("包含: 白色路网 / 12处地名文字 / 搜索框UI / 河道 / 建筑块")
