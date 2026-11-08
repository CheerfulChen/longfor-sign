import random

import math

from typing import List, Tuple

import time

def generate_trajectory_enhanced(
    distance: int,
    duration_ms: int = None,
    sample_interval_ms: int = 10
) -> List[Tuple[int, int, int]]:
    """
    生成增强版的滑动轨迹（更密集、更真实）

    Args:
        distance: 需要滑动的距离(像素)
        duration_ms: 总时长(毫秒)，None 则自动计算(800-1500ms)
        sample_interval_ms: 采样间隔(毫秒)，默认 10ms

    Returns:
        [(x, y, t), ...]: 轨迹点列表 (x坐标, y坐标偏移, 时间戳ms)
    """
    # 自动计算合理的时长
    if duration_ms is None:
        # 根据距离计算：大约 4-8 像素/毫秒
        duration_ms = int(distance * random.uniform(5, 8))
        duration_ms = max(800, min(2000, duration_ms))  # 限制在 800-2000ms

    trajectory = []

    # 使用三次贝塞尔曲线生成速度曲线
    # 控制点决定了加速和减速的程度
    p0, p1, p2, p3 = 0.0, 0.3, 0.7, 1.0  # 标准的缓入缓出曲线

    # 添加随机性
    p1 += random.uniform(-0.1, 0.1)
    p2 += random.uniform(-0.1, 0.1)

    # 时间步数
    steps = duration_ms // sample_interval_ms

    for i in range(steps + 1):
        # 当前时间进度 (0-1)
        t_progress = i / steps

        # 三次贝塞尔曲线计算位置进度
        # B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
        x_progress = (
            (1 - t_progress) ** 3 * p0 +
            3 * (1 - t_progress) ** 2 * t_progress * p1 +
            3 * (1 - t_progress) * t_progress ** 2 * p2 +
            t_progress ** 3 * p3
        )

        # 计算当前 x 位置
        x = int(distance * x_progress)

        # 添加 y 方向的抖动（模拟手抖）
        # 使用正弦波 + 随机噪声
        sine_shake = math.sin(t_progress * math.pi * random.uniform(2, 4)) * 2
        random_shake = random.uniform(-1, 1)
        y = int(sine_shake + random_shake)

        # 当前时间戳
        t = i * sample_interval_ms

        # 添加轻微的时间抖动（模拟真实的事件触发间隔）
        if i > 0:
            t += random.randint(-3, 3)

        trajectory.append((x, y, t))

    # 确保最后一个点精确到达目标
    if trajectory[-1][0] != distance:
        last_t = trajectory[-1][2]
        trajectory.append((distance, 0, last_t + sample_interval_ms))

    return trajectory

def add_realistic_shake(trajectory: List[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
    """
    添加更真实的结尾抖动（模拟人类微调）

    真实行为模式：
    1. 快速接近目标
    2. 小幅回弹
    3. 多次微调
    4. 最终稳定
    """
    if not trajectory:
        return trajectory

    target_x = trajectory[-1][0]
    last_y = trajectory[-1][1]
    current_t = trajectory[-1][2]

    # 1. 轻微超调（约 10-20% 的用户会超调）
    if random.random() < 0.15:
        overshoot = random.randint(2, 5)
        current_t += random.randint(8, 15)
        trajectory.append((target_x + overshoot, last_y + random.randint(-1, 1), current_t))

    # 2. 回弹到目标附近
    shake_count = random.randint(5, 10)
    for i in range(shake_count):
        # 抖动幅度逐渐减小
        decay = 1 - (i / shake_count)

        x_shake = target_x + int(random.uniform(-3, 3) * decay)
        y_shake = random.randint(-1, 1)
        current_t += random.randint(8, 20)

        trajectory.append((x_shake, y_shake, current_t))

    # 3. 最终稳定在目标位置
    current_t += random.randint(15, 40)
    trajectory.append((target_x, 0, current_t))

    return trajectory

def add_mouse_down_up_events(trajectory: List[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
    """
    在开始和结束时添加鼠标按下/抬起事件的停顿

    真实行为：
    - 鼠标按下前有短暂停留（定位）
    - 鼠标抬起后有短暂停留（确认）
    """
    if not trajectory:
        return trajectory

    # 在开始前添加短暂停留（50-150ms）
    start_pause = random.randint(50, 150)
    trajectory = [(x, y, t + start_pause) for x, y, t in trajectory]

    # 在开始位置添加按下前的停留点
    trajectory.insert(0, (0, 0, 0))
    trajectory.insert(0, (0, 0, random.randint(30, 80)))

    # 在结束后添加短暂停留（30-100ms）
    last_x, last_y, last_t = trajectory[-1]
    trajectory.append((last_x, last_y, last_t + random.randint(30, 100)))

    return trajectory

def interpolate_trajectory(
    trajectory: List[Tuple[int, int, int]],
    target_points: int = None
) -> List[Tuple[int, int, int]]:
    """
    插值轨迹以增加点数（如果点数不够）

    Args:
        trajectory: 原始轨迹
        target_points: 目标点数，None 则自动计算

    Returns:
        插值后的轨迹
    """
    if len(trajectory) < 2:
        return trajectory

    if target_points is None:
        # 自动计算：根据时长，大约每 10-15ms 一个点
        duration = trajectory[-1][2] - trajectory[0][2]
        target_points = duration // 12

    if len(trajectory) >= target_points:
        return trajectory

    # 计算需要插入多少点
    points_to_add = target_points - len(trajectory)

    # 在现有点之间均匀插入
    interpolated = [trajectory[0]]

    for i in range(len(trajectory) - 1):
        x1, y1, t1 = trajectory[i]
        x2, y2, t2 = trajectory[i + 1]

        interpolated.append(trajectory[i])

        # 计算这一段需要插入多少点
        segment_ratio = (t2 - t1) / (trajectory[-1][2] - trajectory[0][2])
        segment_points = max(1, int(points_to_add * segment_ratio))

        # 插值
        for j in range(1, segment_points + 1):
            ratio = j / (segment_points + 1)
            x = int(x1 + (x2 - x1) * ratio)
            y = int(y1 + (y2 - y1) * ratio)
            t = int(t1 + (t2 - t1) * ratio)
            interpolated.append((x, y, t))

    interpolated.append(trajectory[-1])

    return interpolated

def generate_realistic_trajectory(
    distance: int,
    duration_ms: int = None,
    min_points: int = 50,
    max_points: int = 150
) -> List[Tuple[int, int, int]]:
    """
    生成非常接近真实人类的完整轨迹（推荐使用）

    Args:
        distance: 滑动距离
        duration_ms: 总时长（None 则自动）
        min_points: 最小点数
        max_points: 最大点数

    Returns:
        完整的轨迹点列表
    """
    # 1. 生成基础密集轨迹
    trajectory = generate_trajectory_enhanced(distance, duration_ms, sample_interval_ms=10)

    # 2. 确保点数在合理范围内
    if len(trajectory) < min_points:
        trajectory = interpolate_trajectory(trajectory, min_points)
    elif len(trajectory) > max_points:
        # 随机采样以减少点数
        indices = sorted(random.sample(range(len(trajectory)), max_points))
        trajectory = [trajectory[i] for i in indices]

    # 3. 添加真实的结尾抖动
    trajectory = add_realistic_shake(trajectory)

    # 4. 添加鼠标按下/抬起的停顿
    trajectory = add_mouse_down_up_events(trajectory)

    return trajectory
