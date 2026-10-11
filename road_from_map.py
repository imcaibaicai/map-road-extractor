"""
road_from_map.py — 从地图截图自动提取可寻路的道路网络

用法:
    python road_from_map.py --image map.png --out ./out
    python road_from_map.py --image map.png --out ./out --crop 40,100,2580,1800
    python road_from_map.py --image map.png --out ./out --cell 14 --density 0.18

原理（四步）:
    1. 阈值掩膜   地图道路通常画成高亮白色线条 → 按「高亮度 + 低饱和度」挑出
    2. 形态学净化 开运算削掉文字/图标的细笔画，闭运算把削断的路面接回
    3. 裁切       去掉地图自带的搜索框、工具栏与城外区域
    4. 栅格化     前景膨胀弥合断口后按格内密度建网格，游程编码压缩，供 Dijkstra 寻路

依赖: numpy, pillow, scipy
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage


# ------------------------------------------------------------------ 工具
def disk(radius: int) -> np.ndarray:
    """圆盘结构元（比方形结构元少引入直角伪影）。"""
    yy, xx = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    return xx * xx + yy * yy <= radius * radius


# ------------------------------------------------------------------ 1. 掩膜
def extract_mask(arr: np.ndarray, min_channel: int, max_sat: int) -> np.ndarray:
    """按「高亮度 + 低饱和度」阈值挑出道路像素。"""
    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)
    hi = np.maximum(np.maximum(r, g), b)
    lo = np.minimum(np.minimum(r, g), b)
    return (lo >= min_channel) & ((hi - lo) <= max_sat)


# ------------------------------------------------------------------ 2. 形态学净化
def denoise(mask: np.ndarray, open_r: int, close_r: int,
            verbose: bool = True) -> np.ndarray:
    """
    开运算 + 闭运算。

    为什么是这两步：
      - 地图上的地名文字笔画细（约 3~5px），开运算会把它们整段削掉；
      - 开运算同时会把路面的细颈削断，闭运算再把断口接回；
      - 顺序不能反：先闭后开会让文字和路面粘连，反而更难清理。
    """
    if open_r > 0:
        mask = ndimage.binary_opening(mask, structure=disk(open_r))
    if close_r > 0:
        mask = ndimage.binary_closing(mask, structure=disk(close_r))
    if verbose:
        print(f"  [denoise] 开运算 r={open_r} + 闭运算 r={close_r} -> {int(mask.sum())} px")
    return mask


def drop_specks(mask: np.ndarray, min_area: int, verbose: bool = True) -> np.ndarray:
    """丢掉孤立小碎点（残留的标点、抗锯齿毛刺）。"""
    if min_area <= 0:
        return mask
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    keep[1:] = sizes >= min_area
    out = keep[lab]
    if verbose:
        print(f"  [specks] 碎点剔除 {n - int(keep.sum())} 个 -> {int(out.sum())} px")
    return out


# ------------------------------------------------------------------ 3. 裁切
def auto_crop_box(mask: np.ndarray, margin_ratio: float):
    """取最大连通域外接矩形，向外扩 margin —— 自动框住主路网、丢掉城外孤路。"""
    lab, n = ndimage.label(mask)
    if n == 0:
        h, w = mask.shape
        return 0, 0, w, h
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    biggest = int(np.argmax(sizes)) + 1
    sl = ndimage.find_objects(lab)[biggest - 1]
    ys, xs = sl
    h, w = mask.shape
    mx = int((xs.stop - xs.start) * margin_ratio)
    my = int((ys.stop - ys.start) * margin_ratio)
    return (max(0, xs.start - mx), max(0, ys.start - my),
            min(w, xs.stop + mx), min(h, ys.stop + my))


# ------------------------------------------------------------------ 4. 栅格化
def build_grid(mask: np.ndarray, cell: int, density_min: float, dilate_px: int):
    """
    栅格化。先前景膨胀弥合断口 —— 这一步很关键：
    细路面在抽样时容易断开，会让 Dijkstra 绕远好几倍。
    注意膨胀只用于寻路层，可视化层始终用未膨胀的掩膜保持贴合。
    """
    m = ndimage.binary_dilation(mask, iterations=dilate_px) if dilate_px > 0 else mask
    h, w = m.shape
    gh, gw = h // cell, w // cell
    if gh == 0 or gw == 0:
        raise ValueError(f"cell={cell} 过大，{w}x{h} 的图切不出网格")
    blocks = m[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell)
    return blocks.mean(axis=(1, 3)) >= density_min, gw, gh


def grid_to_rle(road: np.ndarray):
    """按行游程编码。实测 5000+ 道路格可压到 ~10KB JSON。"""
    gh, gw = road.shape
    rows = []
    for r in range(gh):
        runs, c = [], 0
        while c < gw:
            if road[r, c]:
                s = c
                while c < gw and road[r, c]:
                    c += 1
                runs.append([s, c - 1])
            else:
                c += 1
        rows.append(runs)
    return rows


# ------------------------------------------------------------------ 5. 输出
def render_overlay(mask: np.ndarray, rgba=(0, 170, 255, 170)) -> Image.Image:
    h, w = mask.shape
    buf = np.zeros((h, w, 4), dtype=np.uint8)
    buf[mask] = list(rgba)
    return Image.fromarray(buf, "RGBA")


def png_b64(img: Image.Image):
    bio = io.BytesIO()
    img.save(bio, format="PNG", optimize=True)
    raw = bio.getvalue()
    return base64.b64encode(raw).decode("ascii"), len(raw)


# ------------------------------------------------------------------ 主流程
def run(args):
    src = Image.open(args.image).convert("RGB")
    arr = np.array(src)
    h, w = arr.shape[:2]
    print(f"[1/5] 载入 {args.image}  {w}x{h}")

    mask = extract_mask(arr, args.min_channel, args.max_sat)
    print(f"[2/5] 阈值掩膜 {int(mask.sum())} px ({mask.sum() / (w * h) * 100:.2f}%)")

    # ---- 两份掩膜：视觉层 / 寻路层 ----
    # 形态学开运算去文字的同时会把细路面削断，直接拿去寻路会断链绕远。
    # 所以视觉层用净化后的（干净好看），寻路层用未净化的原始掩膜（连通完整）。
    mask_route = mask
    mask_visual = denoise(mask, args.open_r, args.close_r) if args.visual_clean else mask
    mask_visual = drop_specks(mask_visual, args.min_area)

    if args.crop:
        x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
        print(f"[3/5] 指定裁切 ({x0},{y0})-({x1},{y1})")
    elif args.no_crop:
        x0, y0, x1, y1 = 0, 0, w, h
        print("[3/5] 跳过裁切")
    else:
        x0, y0, x1, y1 = auto_crop_box(mask_route, args.crop_margin)
        print(f"[3/5] 自动裁切 ({x0},{y0})-({x1},{y1})")

    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    mask_c = mask_visual[y0:y1, x0:x1]       # 视觉
    mask_r = mask_route[y0:y1, x0:x1]        # 寻路
    src_c = src.crop((x0, y0, x1, y1))

    road, gw, gh = build_grid(mask_r, args.cell, args.density, args.dilate)
    print(f"[4/5] 寻路网格 {gw}x{gh} (cell={args.cell}px), 道路格 {int(road.sum())}")
    print(f"      视觉层 {int(mask_c.sum())} px ｜ 寻路层 {int(mask_r.sum())} px")

    os.makedirs(args.out, exist_ok=True)
    ov = render_overlay(mask_c)
    b64, nbytes = png_b64(ov)
    ov.save(os.path.join(args.out, "road_overlay.png"))
    with open(os.path.join(args.out, "road_overlay_b64.txt"), "w") as f:
        f.write(b64)
    src_c.save(os.path.join(args.out, "base_map_cropped.png"))

    payload = {
        "cell": args.cell, "gw": gw, "gh": gh,
        "rows": grid_to_rle(road),
        "crop": [x0, y0, x1, y1],
        "width": x1 - x0, "height": y1 - y0,
    }
    with open(os.path.join(args.out, "roadgrid.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    dbg = np.array(src_c)
    dbg[mask_c] = [220, 30, 30]
    Image.fromarray(dbg).save(os.path.join(args.out, "debug_overlay_on_map.png"))
    Image.fromarray((mask_c * 255).astype(np.uint8), "L").save(
        os.path.join(args.out, "roads_only.png"))

    print(f"[5/5] 输出目录 {args.out}/")
    for name in ("roadgrid.json", "road_overlay.png", "base_map_cropped.png",
                 "roads_only.png", "debug_overlay_on_map.png"):
        fp = os.path.join(args.out, name)
        print(f"      {name:26s} {os.path.getsize(fp)} B")
    print(f"\n速度标定参考：骑行约 {args.px_per_min:.0f} px/分钟")
    print(f"（即 routeMinutes ≈ gridPathLength × cell / {args.px_per_min:.0f}）")


def main():
    p = argparse.ArgumentParser(
        description="从地图截图提取可寻路的道路网络",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--image", required=True, help="输入地图截图")
    p.add_argument("--out", default="roads_out", help="输出目录")

    g = p.add_argument_group("掩膜阈值")
    g.add_argument("--min-channel", type=int, default=243,
                   help="RGB 最小值下限。调大更严格（只挑更白的路面）")
    g.add_argument("--max-sat", type=int, default=9,
                   help="RGB 极差上限。调小更严格（只挑更灰白的路面）")

    g = p.add_argument_group("形态学净化（只作用于视觉层）")
    g.add_argument("--visual-clean", dest="visual_clean", action="store_true", default=True,
                   help="净化视觉层掩膜（去文字）。寻路层始终使用原始掩膜以保证连通")
    g.add_argument("--no-visual-clean", dest="visual_clean", action="store_false",
                   help="视觉层也不净化（保留文字，但路面连续）")
    g.add_argument("--open-r", type=int, default=2,
                   help="开运算半径。地名笔画约 3~5px，取 2 可整段削掉；取 0 关闭")
    g.add_argument("--close-r", type=int, default=3,
                   help="闭运算半径。把开运算削断的路面接回；取 0 关闭")
    g.add_argument("--min-area", type=int, default=260,
                   help="孤立碎点面积阈值")

    g = p.add_argument_group("裁切")
    g.add_argument("--crop", default=None, help="显式裁切框 x0,y0,x1,y1（用来去掉地图自带搜索框/工具栏）")
    g.add_argument("--no-crop", action="store_true", help="完全不裁切")
    g.add_argument("--crop-margin", type=float, default=0.02,
                   help="自动裁切时向外扩张比例")

    g = p.add_argument_group("寻路网格")
    g.add_argument("--cell", type=int, default=14, help="网格边长（像素）")
    g.add_argument("--density", type=float, default=0.18,
                   help="格内路面占比达到该值即视为道路格")
    g.add_argument("--dilate", type=int, default=5,
                   help="网格化前的膨胀像素数，弥合断口防止绕远")

    g = p.add_argument_group("速度标定")
    g.add_argument("--px-per-min", type=float, default=400.0,
                   help="骑行像素/分钟（用于把像素长度换算成时间）")

    run(p.parse_args())


if __name__ == "__main__":
    main()
