#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心测试引擎
包含压测的核心逻辑：请求发送、工作协程、结果统计等
"""

import asyncio
import aiohttp
import time
import statistics
import os
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime


class LoadTestResult:
    """压测结果统计"""

    def __init__(self, t1: float = 1.0, t2: float = 3.0):
        self.response_times: List[float] = []
        self.fast_count = 0  # 快速请求（响应时间 < T1）
        self.slow_count = 0  # 慢请求（T1 ≤ 响应时间 ≤ T2）
        self.bad_count = 0   # 坏请求（响应时间 > T2 或超时/失败）
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.errors: List[str] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.t1 = t1  # 快速阈值（默认1秒）
        self.t2 = t2  # 慢速阈值（默认3秒）

    def add_result(self, response_time: float, status_code: int, error: Optional[str] = None):
        """添加一次请求结果"""
        self.response_times.append(response_time)

        # 三档统计逻辑
        if status_code == 200:
            # HTTP 200 成功请求，根据响应时间分类
            if response_time < self.t1:
                self.fast_count += 1  # fast: < T1
            elif response_time <= self.t2:
                self.slow_count += 1  # slow: T1 ~ T2
            else:
                self.bad_count += 1  # bad: > T2
        else:
            # HTTP 非200 或超时，视为 bad
            self.bad_count += 1
            if error:
                self.errors.append(error)

        self.status_codes[status_code] += 1

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        if not self.response_times:
            return {}

        sorted_times = sorted(self.response_times)
        total_requests = len(self.response_times)

        stats = {
            'total_requests': total_requests,
            'fast_count': self.fast_count,  # 快速请求数
            'slow_count': self.slow_count,   # 慢请求数
            'bad_count': self.bad_count,    # 坏请求数
            'fast_rate': (self.fast_count / total_requests * 100) if total_requests > 0 else 0,  # 快速请求率
            'slow_rate': (self.slow_count / total_requests * 100) if total_requests > 0 else 0,  # 慢请求率
            'bad_rate': (self.bad_count / total_requests * 100) if total_requests > 0 else 0,   # 坏请求率
            'status_codes': dict(self.status_codes),
            'response_time': {
                'min': min(self.response_times),
                'max': max(self.response_times),
                'mean': statistics.mean(self.response_times),
                'median': statistics.median(self.response_times),
            },
            't1': self.t1,  # 快速阈值
            't2': self.t2   # 慢速阈值
        }

        # 计算百分位数
        if total_requests > 0:
            stats['response_time']['p50'] = sorted_times[int(total_requests * 0.50)]
            stats['response_time']['p90'] = sorted_times[int(total_requests * 0.90)]
            stats['response_time']['p95'] = sorted_times[int(total_requests * 0.95)]
            stats['response_time']['p99'] = sorted_times[int(total_requests * 0.99)]

        # 计算QPS
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            stats['duration'] = duration
            stats['qps'] = total_requests / duration if duration > 0 else 0

        return stats

    def generate_report_text(self, test_config: Optional[Dict] = None) -> str:
        """生成测试报告文本"""
        stats = self.get_statistics()
        lines = []

        lines.append("="*80)
        lines.append("压测报告")
        lines.append("="*80)
        lines.append(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if test_config:
            lines.append(f"\n【测试配置】")
            for key, value in test_config.items():
                lines.append(f"  {key}: {value}")

        lines.append(f"\n【请求统计】（三档分类）")
        t1 = stats.get('t1', 1.0)
        t2 = stats.get('t2', 3.0)
        lines.append(f"  总请求数: {stats['total_requests']}")
        lines.append(f"  快速请求 (fast): {stats['fast_count']} (响应时间 < {t1:.1f}秒) - {stats['fast_rate']:.2f}%")
        lines.append(f"  慢速请求 (slow): {stats['slow_count']} ({t1:.1f}秒 ≤ 响应时间 ≤ {t2:.1f}秒) - {stats['slow_rate']:.2f}%")
        lines.append(f"  坏请求 (bad): {stats['bad_count']} (响应时间 > {t2:.1f}秒 或超时/失败) - {stats['bad_rate']:.2f}%")

        if stats.get('duration'):
            lines.append(f"\n【性能统计】")
            lines.append(f"  测试时长: {stats['duration']:.2f} 秒")
            lines.append(f"  QPS: {stats['qps']:.2f}")

        lines.append(f"\n【响应时间统计】(单位: 秒)")
        rt = stats['response_time']
        lines.append(f"  最小值: {rt['min']:.3f}s")
        lines.append(f"  最大值: {rt['max']:.3f}s")
        lines.append(f"  平均值: {rt['mean']:.3f}s")
        lines.append(f"  中位数: {rt['median']:.3f}s")
        if 'p50' in rt:
            lines.append(f"  P50: {rt['p50']:.3f}s")
            lines.append(f"  P90: {rt['p90']:.3f}s")
            lines.append(f"  P95: {rt['p95']:.3f}s")
            lines.append(f"  P99: {rt['p99']:.3f}s")

        lines.append(f"\n【HTTP状态码统计】")
        for code, count in sorted(stats['status_codes'].items()):
            lines.append(f"  {code}: {count}")

        if self.errors:
            lines.append(f"\n【错误信息】(前50条)")
            for error in self.errors[:50]:
                lines.append(f"  {error}")
            if len(self.errors) > 50:
                lines.append(f"  ... 还有 {len(self.errors) - 50} 条错误")

        lines.append("="*80)

        return "\n".join(lines)

    def save_report(self, report_text: str, output_dir: str = "test/load_test/reports", test_config: Optional[Dict] = None) -> str:
        """保存报告到文件，返回文件路径"""
        # 创建报告目录
        os.makedirs(output_dir, exist_ok=True)

        # 根据测试模式生成文件名前缀
        mode_prefix = ""
        if test_config:
            if test_config.get('total_requests'):
                mode_prefix = "total"
            elif test_config.get('duration'):
                mode_prefix = "duration"

        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if mode_prefix:
            filename = f"load_test_report_{mode_prefix}_{timestamp}.txt"
        else:
            filename = f"load_test_report_{timestamp}.txt"
        filepath = os.path.join(output_dir, filename)

        # 保存报告
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_text)

        return filepath

    def save_report_json(self, test_config: Optional[Dict] = None, output_dir: str = "test/load_test/reports") -> str:
        """保存JSON格式的报告，返回文件路径"""
        import json

        # 创建报告目录
        os.makedirs(output_dir, exist_ok=True)

        # 根据测试模式生成文件名前缀
        mode_prefix = ""
        if test_config:
            if test_config.get('total_requests'):
                mode_prefix = "total"
            elif test_config.get('duration'):
                mode_prefix = "duration"

        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if mode_prefix:
            filename = f"load_test_report_{mode_prefix}_{timestamp}.json"
        else:
            filename = f"load_test_report_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)

        # 准备JSON数据
        stats = self.get_statistics()
        report_data = {
            'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_config': test_config or {},
            'statistics': stats,
            'errors': self.errors[:100] if self.errors else []  # 只保存前100条错误
        }

        # 保存JSON报告
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        return filepath


async def make_request(
    session: aiohttp.ClientSession,
    url: str,
    payload: Dict,
    timeout: int = 5
) -> Tuple[float, int, Optional[str]]:
    """发送单个请求"""
    start_time = time.time()
    status_code = 0
    error = None

    try:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            status_code = response.status
            response_time = time.time() - start_time

            # 尝试读取响应内容（用于验证）
            try:
                await response.json()
            except:
                await response.text()

            return response_time, status_code, None

    except asyncio.TimeoutError:
        response_time = time.time() - start_time
        error = f"请求超时 (>{timeout}s)"
        return response_time, 0, error

    except aiohttp.ClientError as e:
        response_time = time.time() - start_time
        error = f"客户端错误: {str(e)}"
        return response_time, 0, error

    except Exception as e:
        response_time = time.time() - start_time
        error = f"未知错误: {str(e)}"
        return response_time, 0, error


async def worker(
    session: aiohttp.ClientSession,
    url: str,
    payload: Dict,
    result: LoadTestResult,
    semaphore: asyncio.Semaphore,
    total_requests: Optional[int] = None,
    timeout: int = 5
):
    """工作协程：持续发送请求"""
    while True:
        # 检查是否达到总请求数（在获取信号量之前检查，避免不必要的等待）
        if total_requests is not None:
            current_total = result.fast_count + result.slow_count + result.bad_count
            if current_total >= total_requests:
                break

        async with semaphore:
            # 再次检查（因为可能有并发竞争）
            if total_requests is not None:
                current_total = result.fast_count + result.slow_count + result.bad_count
                if current_total >= total_requests:
                    break

            response_time, status_code, error = await make_request(session, url, payload, timeout)
            result.add_result(response_time, status_code, error)


async def run_load_test(
    url: str,
    concurrent: int,
    total: Optional[int] = None,
    duration: Optional[int] = None,
    payload: Optional[Dict] = None,
    timeout: int = 5,
    t1: float = 1.0,
    t2: float = 3.0
):
    """运行压测"""
    if payload is None:
        payload = {
            "Content": "广东省深圳市龙岗区坂田街道长坑路西2巷2号202 黄大大 18273778575"
        }

    # 使用 T1 和 T2 作为三档统计阈值
    result = LoadTestResult(t1=t1, t2=t2)
    result.start_time = time.time()

    # 创建信号量控制并发数
    semaphore = asyncio.Semaphore(concurrent)

    # 创建HTTP会话
    connector = aiohttp.TCPConnector(limit=concurrent * 2, limit_per_host=concurrent * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 创建worker任务
        tasks = []

        for _ in range(concurrent):
            task = asyncio.create_task(
                worker(session, url, payload, result, semaphore, total, timeout)
            )
            tasks.append(task)

        # 如果设置了持续时间，在指定时间后停止
        if duration:
            await asyncio.sleep(duration)
            # 取消所有任务
            for task in tasks:
                task.cancel()
            # 等待任务完成
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # 等待所有任务完成
            await asyncio.gather(*tasks)

    result.end_time = time.time()
    return result
