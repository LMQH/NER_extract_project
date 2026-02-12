#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告生成器
负责各种测试报告的生成和保存
"""

import os
from typing import List, Dict, Optional
from datetime import datetime

from .load_test_core import LoadTestResult


def generate_summary_report(
    batch_results: List[Dict],
    batch_param: str,
    base_config: Dict,
    output_dir: str
) -> str:
    """
    生成批量测试汇总报告

    Args:
        batch_results: 批量测试结果列表
        batch_param: 批量参数名称（如 'concurrent', 'total'）
        base_config: 基础配置
        output_dir: 输出目录

    Returns:
        汇总报告文本
    """
    lines = []

    lines.append("="*80)
    lines.append("批量压测汇总报告")
    lines.append("="*80)
    lines.append(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    lines.append(f"\n【测试配置】")
    lines.append(f"  URL: {base_config.get('url', 'N/A')}")
    lines.append(f"  批量参数: {batch_param}")
    lines.append(f"  测试参数值: {[r['param_value'] for r in batch_results]}")

    # 固定参数
    fixed_params = []
    if base_config.get('total') and not isinstance(base_config.get('total'), list):
        fixed_params.append(f"total={base_config['total']}")
    if base_config.get('duration') and not isinstance(base_config.get('duration'), list):
        fixed_params.append(f"duration={base_config['duration']}秒")
    if base_config.get('timeout'):
        fixed_params.append(f"timeout={base_config['timeout']}秒")
    if fixed_params:
        lines.append(f"  固定参数: {', '.join(fixed_params)}")

    # 获取T1和T2阈值（从第一个结果中获取）
    t1 = batch_results[0]['result'].t1 if batch_results else 1.0
    t2 = batch_results[0]['result'].t2 if batch_results else 3.0

    lines.append(f"\n【性能对比表】（三档分类: fast<{t1:.1f}s, slow {t1:.1f}s~{t2:.1f}s, bad>{t2:.1f}s）")
    # 表头
    header = f"{batch_param:>12} | {'总请求':>8} | {'Fast':>6} | {'Slow':>6} | {'Bad':>6} | {'Fast率':>8} | {'Slow率':>8} | {'Bad率':>8} | {'QPS':>10} | {'平均响应时间':>14} | {'P95响应时间':>14}"
    lines.append(header)
    lines.append("-" * len(header))

    # 数据行
    for result in batch_results:
        stats = result['result'].get_statistics()
        param_val = result['param_value']
        total_req = stats.get('total_requests', 0)
        fast = stats.get('fast_count', 0)
        slow = stats.get('slow_count', 0)
        bad = stats.get('bad_count', 0)
        fast_rate = stats.get('fast_rate', 0)
        slow_rate = stats.get('slow_rate', 0)
        bad_rate = stats.get('bad_rate', 0)
        qps = stats.get('qps', 0)
        avg_rt = stats.get('response_time', {}).get('mean', 0)
        p95_rt = stats.get('response_time', {}).get('p95', 0)

        row = f"{param_val:>12} | {total_req:>8} | {fast:>6} | {slow:>6} | {bad:>6} | {fast_rate:>7.2f}% | {slow_rate:>7.2f}% | {bad_rate:>7.2f}% | {qps:>10.2f} | {avg_rt:>13.3f}s | {p95_rt:>13.3f}s"
        lines.append(row)

    # 性能趋势分析
    lines.append(f"\n【性能趋势分析】")

    # 找出QPS峰值
    max_qps_result = max(batch_results, key=lambda r: r['result'].get_statistics().get('qps', 0))
    max_qps = max_qps_result['result'].get_statistics().get('qps', 0)
    max_qps_param = max_qps_result['param_value']
    lines.append(f"- QPS峰值: {max_qps:.2f} ({batch_param}={max_qps_param})")

    # 找出最优配置（Fast率>80%且QPS较高）
    best_results = [r for r in batch_results if r['result'].get_statistics().get('fast_rate', 0) >= 80]
    if best_results:
        best_result = max(best_results, key=lambda r: r['result'].get_statistics().get('qps', 0))
        best_qps = best_result['result'].get_statistics().get('qps', 0)
        best_fast_rate = best_result['result'].get_statistics().get('fast_rate', 0)
        best_bad_rate = best_result['result'].get_statistics().get('bad_rate', 0)
        best_param = best_result['param_value']
        lines.append(f"- 推荐配置: {batch_param}={best_param} (QPS={best_qps:.2f}, Fast率={best_fast_rate:.2f}%, Bad率={best_bad_rate:.2f}%)")

    # 响应时间趋势
    rt_values = [r['result'].get_statistics().get('response_time', {}).get('mean', 0) for r in batch_results]
    if len(rt_values) > 1:
        rt_increase = rt_values[-1] - rt_values[0]
        if rt_increase > 0.1:
            lines.append(f"- 响应时间变化: 从 {rt_values[0]:.3f}s 增加到 {rt_values[-1]:.3f}s (增加 {rt_increase:.3f}s)")
            # 找出响应时间明显上升的点
            for i in range(1, len(rt_values)):
                if rt_values[i] - rt_values[i-1] > rt_values[0] * 0.3:  # 增加超过30%
                    lines.append(f"- 响应时间拐点: {batch_param}={batch_results[i-1]['param_value']} -> {batch_results[i]['param_value']}")
                    break

    # 详细报告链接
    lines.append(f"\n【详细报告】")
    lines.append("每个测试的详细报告已单独保存:")
    for i, result in enumerate(batch_results, 1):
        report_file = result.get('report_file', 'N/A')
        lines.append(f"  {i}. {batch_param}={result['param_value']}: {os.path.basename(report_file)}")

    lines.append("="*80)

    return "\n".join(lines)


def save_reports(
    result: LoadTestResult,
    test_config: Dict,
    output_dir: str,
    save_json: bool = False
) -> Dict[str, str]:
    """
    统一的报告保存接口

    Args:
        result: 测试结果对象
        test_config: 测试配置
        output_dir: 输出目录
        save_json: 是否保存JSON报告

    Returns:
        {
            'text_report': 'path/to/text_report.txt',
            'json_report': 'path/to/json_report.json'  # 可选
        }
    """
    report_text = result.generate_report_text(test_config)
    text_file = result.save_report(report_text, output_dir, test_config)

    reports = {'text_report': text_file}

    if save_json:
        json_file = result.save_report_json(test_config, output_dir)
        reports['json_report'] = json_file

    return reports
