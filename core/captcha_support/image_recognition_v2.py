import cv2

import numpy as np

from typing import Tuple, List

import os

_DEBUG_DIR = os.path.dirname(os.path.abspath(__file__))

def find_gap_position_v2(bg_image_path: str, slider_image_path: str, debug: bool = False, method: str = "shape", apply_legacy_offset: bool = True) -> Tuple[int, int]:
    """
    改进的缺口识别算法 - 多方法融合

    Args:
        bg_image_path: 背景图路径
        slider_image_path: 滑块图路径
        debug: 是否保存调试信息
        method: 使用的方法 ("auto", "contour", "color", "shape")

    Returns:
        (x, y): 缺口位置坐标
    """
    # 1. 读取图片
    bg = cv2.imread(bg_image_path)
    if bg is None:
        raise ValueError(f"无法读取背景图: {bg_image_path}")

    slider = cv2.imread(slider_image_path, cv2.IMREAD_UNCHANGED)
    if slider is None:
        raise ValueError(f"无法读取滑块图: {slider_image_path}")

    print(f"   背景图尺寸: {bg.shape}")
    print(f"   滑块图尺寸: {slider.shape}")

    if debug:
        print("\n   === 各方法检测结果 ===")

    # 2. 方法1：基于边缘的轮廓检测（最准确）
    x1, y1, confidence1 = detect_by_contour(bg, slider, debug)
    if debug:
        print(f"   方法1 (轮廓检测): x={x1}px, 置信度={confidence1:.2f}")

    # 3. 方法2：颜色差异检测
    x2, y2, confidence2 = detect_by_color_diff(bg, slider, debug)
    if debug:
        print(f"   方法2 (颜色差异): x={x2}px, 置信度={confidence2:.2f}")

    # 4. 方法3：滑块形状匹配
    x3, y3, confidence3 = detect_by_shape_match(bg, slider, debug)
    if debug:
        print(f"   方法3 (形状匹配): x={x3}px, 置信度={confidence3:.2f}")
        print(f"   =======================\n")

    # 5. 选择最佳结果
    if method == "contour":
        # 强制使用轮廓检测
        x, y = x1, y1
        best_method = "轮廓检测（强制）"
    elif method == "color":
        # 强制使用颜色差异
        x, y = x2, y2
        best_method = "颜色差异（强制）"
    elif method == "shape":
        # 强制使用形状匹配
        x, y = x3, y3
        best_method = "形状匹配（强制）"
    else:
        # 自动选择（方法3形状匹配优先）
        # 如果方法3置信度高，直接使用
        if confidence3 > 0.5:
            x, y = x3, y3
            best_method = "形状匹配（高置信度）"
        # 否则使用加权平均，但方法3权重 x3
        elif confidence3 > 0:
            # 提高方法3的权重（乘以3）
            weighted_confidence3 = confidence3 * 3
            total_confidence = confidence1 + confidence2 + weighted_confidence3
            x = int((x1 * confidence1 + x2 * confidence2 + x3 * weighted_confidence3) / total_confidence)
            y = int((y1 * confidence1 + y2 * confidence2 + y3 * weighted_confidence3) / total_confidence)
            best_method = "加权平均（形状匹配权重x3）"
        else:
            # 备选：使用轮廓法
            x, y = x1, y1
            best_method = "轮廓检测（备选）"

    # 6. 应用偏移修正
    # 滑块起始位置的偏移量
    OFFSET = 91 if apply_legacy_offset else 0
    x_detected = x
    x_adjusted = max(0, x - OFFSET)

    if debug:
        print(f"   - 检测到的 x: {x_detected}px")
        print(f"   - 偏移修正: -{OFFSET}px")
        print(f"   ✓ 最终结果: x={x_adjusted}, y={y}")
        print(f"   选择方法: {best_method}")
        print(f"   说明: 最终 x 是需要滑动的距离")
        # 在原图上标记
        result_img = bg.copy()
        # 标记偏移起点（蓝色）
        cv2.circle(result_img, (OFFSET, y), 5, (255, 0, 0), -1)
        cv2.putText(result_img, f"Start: {OFFSET}px", (OFFSET+10, y-20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        # 标记检测到的缺口位置（黄色）
        cv2.circle(result_img, (x_detected, y), 5, (0, 255, 255), -1)
        cv2.putText(result_img, f"Gap: {x_detected}px", (x_detected+10, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        # 绘制滑动距离（绿色箭头）
        cv2.arrowedLine(result_img, (OFFSET, y), (x_detected, y), (0, 255, 0), 3)
        cv2.putText(result_img, f"Distance: {x_adjusted}px",
                    (OFFSET + (x_detected-OFFSET)//2, y+30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imwrite(os.path.join(_DEBUG_DIR, "debug_final_result.png"), result_img)

    return x_adjusted, y

def detect_by_contour(bg: np.ndarray, slider: np.ndarray, debug: bool = False) -> Tuple[int, int, float]:
    """
    方法1：基于轮廓检测
    原理：滑块缺口处会有明显的边缘断裂
    """
    # 转灰度
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)

    # 边缘检测
    bg_edges = cv2.Canny(bg_gray, 50, 150)

    # 垂直投影：统计每列的边缘像素数
    vertical_projection = np.sum(bg_edges, axis=0)

    # 寻找投影的峰值（边缘突变处）
    # 使用一阶差分找到突变位置
    diff = np.diff(vertical_projection)

    # 找到差分绝对值最大的位置（最可能是缺口）
    # 排除图片边缘 20 像素
    margin = 20
    search_area = diff[margin:-margin]
    if len(search_area) == 0:
        return 0, 0, 0.0

    # 找到正向和负向的最大变化
    positive_peaks = np.where(search_area > np.percentile(search_area, 95))[0]
    negative_peaks = np.where(search_area < np.percentile(search_area, 5))[0]

    # 缺口通常是先上升再下降
    candidates = []
    for pos_peak in positive_peaks:
        for neg_peak in negative_peaks:
            if 0 < neg_peak - pos_peak < 100:  # 滑块宽度通常小于 100
                x = pos_peak + margin
                # 计算置信度（基于峰值高度）
                confidence = abs(search_area[pos_peak]) + abs(search_area[neg_peak])
                candidates.append((x, confidence))

    if candidates:
        # 选择置信度最高的
        x, confidence = max(candidates, key=lambda c: c[1])
        # 归一化置信度
        confidence = min(confidence / 10000, 1.0)
    else:
        # 没有找到候选，使用投影最大值
        x = np.argmax(vertical_projection)
        confidence = 0.3

    # y 坐标估计（通常在图片中上部）
    y = bg.shape[0] // 3

    if debug:
        cv2.imwrite(os.path.join(_DEBUG_DIR, "debug_contour_edges.png"), bg_edges)
        # 保存投影图
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 8))
            ax1.plot(vertical_projection)
            ax1.axvline(x, color='r', linestyle='--', label=f'x={x}')
            ax1.set_title('Vertical Edge Projection')
            ax1.legend()

            ax2.plot(diff)
            ax2.axvline(x-margin, color='r', linestyle='--')
            ax2.set_title('First Derivative')

            plt.savefig(os.path.join(_DEBUG_DIR, 'debug_contour_projection.png'))
            plt.close()
        except:
            pass

    return x, y, confidence

def detect_by_color_diff(bg: np.ndarray, slider: np.ndarray, debug: bool = False) -> Tuple[int, int, float]:
    """
    方法2：基于颜色差异
    原理：缺口处的颜色与周围有明显差异
    """
    # 转换到 LAB 颜色空间（对亮度变化更敏感）
    bg_lab = cv2.cvtColor(bg, cv2.COLOR_BGR2LAB)

    # 计算每列的颜色标准差
    h, w = bg_lab.shape[:2]
    col_std = np.zeros(w)

    for i in range(w):
        col_std[i] = np.std(bg_lab[:, i, :])

    # 使用滑动窗口找到标准差突变最大的位置
    window_size = 10
    max_diff = 0
    best_x = 0

    for i in range(window_size, w - window_size):
        left_avg = np.mean(col_std[i-window_size:i])
        right_avg = np.mean(col_std[i:i+window_size])
        diff = abs(right_avg - left_avg)

        if diff > max_diff:
            max_diff = diff
            best_x = i

    # 置信度
    confidence = min(max_diff / 50, 1.0)

    # y 坐标
    y = h // 3

    if debug:
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(15, 4))
            plt.plot(col_std)
            plt.axvline(best_x, color='r', linestyle='--', label=f'x={best_x}')
            plt.title('Color Standard Deviation per Column')
            plt.legend()
            plt.savefig(os.path.join(_DEBUG_DIR, 'debug_color_diff.png'))
            plt.close()
        except:
            pass

    return best_x, y, confidence

def detect_by_shape_match(bg: np.ndarray, slider: np.ndarray, debug: bool = False) -> Tuple[int, int, float]:
    """
    方法3：基于滑块形状匹配
    原理：使用滑块的实际轮廓在背景图中查找
    """
    # 处理滑块（提取有效区域）
    if len(slider.shape) == 3 and slider.shape[2] == 4:
        # 有透明通道
        alpha = slider[:, :, 3]

        # 找到非透明区域
        mask = alpha > 128
        if np.sum(mask) == 0:
            return 0, 0, 0.0

        # 提取滑块的边缘
        slider_gray = cv2.cvtColor(slider[:, :, :3], cv2.COLOR_BGR2GRAY)
        # 只保留非透明部分
        slider_gray = cv2.bitwise_and(slider_gray, slider_gray, mask=mask.astype(np.uint8) * 255)
    else:
        slider_gray = cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY)
        mask = np.ones(slider_gray.shape, dtype=bool)

    # 滑块边缘检测
    slider_edges = cv2.Canny(slider_gray, 50, 150)

    # 在背景图中进行模板匹配
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    bg_edges = cv2.Canny(bg_gray, 50, 150)

    # 使用归一化相关系数匹配
    result = cv2.matchTemplate(bg_edges, slider_edges, cv2.TM_CCOEFF_NORMED)

    # 找到最佳匹配位置
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    x, y = max_loc
    # 取识别框中线：(右 - 左) / 2 + 左
    h, w = slider_edges.shape
    x = x + w // 2
    confidence = max_val

    if debug:
        cv2.imwrite(os.path.join(_DEBUG_DIR, "debug_shape_slider_edges.png"), slider_edges)
        cv2.imwrite(os.path.join(_DEBUG_DIR, "debug_shape_bg_edges.png"), bg_edges)

        # 在结果上标记（x 已是中线，还原左右边界用于绘制矩形）
        result_img = bg.copy()
        x_left = x - w // 2
        cv2.rectangle(result_img, (x_left, y), (x_left + w, y + h), (0, 255, 0), 2)
        cv2.line(result_img, (x, y), (x, y + h), (0, 0, 255), 2)
        cv2.imwrite("debug_shape_match.png", result_img)

    return x, y, confidence

def find_gap_position(bg_image_path: str, slider_image_path: str, debug: bool = False, method: str = "shape", apply_legacy_offset: bool = True) -> Tuple[int, int]:
    """向后兼容的函数"""
    return find_gap_position_v2(bg_image_path, slider_image_path, debug, method, apply_legacy_offset)
