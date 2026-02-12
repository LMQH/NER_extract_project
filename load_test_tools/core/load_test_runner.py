#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试运行器
提供高级测试流程控制
"""

import asyncio
import os
from typing import List, Dict, Optional

from .load_test_core import run_load_test, LoadTestResult
from .load_test_reporter import save_reports, generate_summary_report


async def run_single_test(
    url: str,
    concurrent: int,
    total: Optional[int] = None,
    duration: Optional[int] = None,
    payload: Optional[Dict] = None,
    timeout: int = 5,
    t1: float = 1.0,
    t2: float = 3.0,
    output_dir: str = 'test/load_test/reports',
    save_json: bool = False,
    test_name: str = "single_test"
) -> LoadTestResult:
    """
    运行单次测试

    Args:
        url: API接口地址
        concurrent: 并发数
        total: 总请求数（与duration二选一）
        duration: 测试持续时间（秒，与total二选一）
        payload: 请求负载
        timeout: 请求超时时间（秒）
        t1: 快速请求阈值（秒）
        t2: 慢速请求阈值（秒）
        output_dir: 报告输出目录
        save_json: 是否保存JSON报告
        test_name: 测试名称

    Returns:
        LoadTestResult: 测试结果
    """
    # 准备测试配置
    test_config = {
        'url': url,
        'concurrent': concurrent,
        'total_requests': total,
        'duration': duration,
        'timeout': timeout,
        'test_name': test_name,
        't1': t1,
        't2': t2
    }

    if payload:
        test_config['content'] = payload.get('Content', '')

    # 运行测试
    result = await run_load_test(
        url=url,
        concurrent=concurrent,
        total=total,
        duration=duration,
        payload=payload,
        timeout=timeout,
        t1=t1,
        t2=t2
    )

    # 保存报告
    reports = save_reports(result, test_config, output_dir, save_json)
    print(f"✓ 报告已保存: {reports['text_report']}")

    return result


async def run_batch_tests(
    test_configs: List[Dict],
    base_config: Dict,
    output_dir: str = 'test/load_test/reports',
    save_json: bool = False,
    cooldown: int = 5
) -> List[Dict]:
    """
    运行批量测试

    Args:
        test_configs: 测试配置列表，每个配置包含并发、总数等参数
        base_config: 基础配置（URL、超时等）
        output_dir: 报告输出目录
        save_json: 是否保存JSON报告
        cooldown: 测试间隔冷却时间（秒）

    Returns:
        批量测试结果列表
    """
    batch_results = []
    total_tests = len(test_configs)

    for idx, test_config in enumerate(test_configs, 1):
        print(f"\n{'='*80}")
        print(f"测试 {idx}/{total_tests}: 并发={test_config.get('concurrent')}")
        print(f"{'='*80}")

        # 合并配置
        config = {**base_config, **test_config}

        # 运行测试
        result = await run_load_test(
            url=config['url'],
            concurrent=config['concurrent'],
            total=config.get('total'),
            duration=config.get('duration'),
            payload={"Content": config.get('content', '')},
            timeout=config.get('timeout', 5),
            t1=config.get('t1', 1.0),
            t2=config.get('t2', 3.0)
        )

        # 保存报告
        report_info = save_reports(result, config, output_dir, save_json)

        # 打印结果摘要
        stats = result.get_statistics()
        print(f"✓ QPS: {stats.get('qps', 0):.2f}")
        print(f"✓ Fast: {stats.get('fast_rate', 0):.2f}%")
        print(f"✓ Bad: {stats.get('bad_rate', 0):.2f}%")

        batch_results.append({
            'param_value': test_config.get('concurrent'),
            'result': result,
            'report_file': report_info['text_report'],
            'test_config': config
        })

        # 冷却时间（最后一次不需要等待）
        if idx < total_tests:
            print(f"\n等待 {cooldown} 秒后继续...")
            await asyncio.sleep(cooldown)

    return batch_results


async def run_sequential_tests(
    test_configs: List[Dict],
    base_config: Dict,
    output_dir: str = 'test/load_test/reports',
    save_json: bool = False,
    cooldown: int = 10,
    generate_summary: bool = True
) -> List[Dict]:
    """
    运行序列测试（多阶段测试）

    与 run_batch_tests 的区别：
    - 自动生成汇总报告
    - 更详细的输出
    - 适用于阶段化测试

    Args:
        test_configs: 测试配置列表
        base_config: 基础配置（URL、超时等）
        output_dir: 报告输出目录
        save_json: 是否保存JSON报告
        cooldown: 测试间隔冷却时间（秒）
        generate_summary: 是否生成汇总报告

    Returns:
        测试结果列表
    """
    batch_results = await run_batch_tests(
        test_configs=test_configs,
        base_config=base_config,
        output_dir=output_dir,
        save_json=save_json,
        cooldown=cooldown
    )

    # 生成汇总报告
    if generate_summary and len(batch_results) > 1:
        print(f"\n{'='*80}")
        print("生成汇总报告...")
        print(f"{'='*80}")

        # 假设批量参数是 concurrent
        summary_text = generate_summary_report(
            batch_results,
            batch_param='concurrent',
            base_config=base_config,
            output_dir=output_dir
        )

        # 保存汇总报告
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = os.path.join(output_dir, f"load_test_summary_{timestamp}.txt")

        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary_text)

        print(f"✓ 汇总报告: {summary_file}")

    return batch_results
