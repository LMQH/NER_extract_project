#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义配置测试
目标: 完全使用环境配置文件来启动测试
"""

import asyncio
import sys
import os

# 动态添加 test/load_test 目录到 Python 路径
# 这样无论项目根目录结构如何，只要 test/load_test 目录结构不变就能工作
script_dir = os.path.dirname(os.path.abspath(__file__))
load_test_dir = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, load_test_dir)

# 直接导入，不依赖项目根目录的包结构
from core.load_test_config import load_config, validate_config
from core.load_test_runner import run_single_test, run_batch_tests, run_sequential_tests

# ==================== 配置文件路径 ====================
# 使用相对路径，基于 test/load_test 目录
script_dir = os.path.dirname(os.path.abspath(__file__))
load_test_dir = os.path.abspath(os.path.join(script_dir, '..'))
CONFIG_FILE = os.path.join(load_test_dir, 'load_test_config.json')

# =========================================================

async def main():
    """主函数"""
    # 加载配置文件
    config = load_config(CONFIG_FILE)

    if not config:
        print(f"错误: 无法加载配置文件 {CONFIG_FILE}")
        return

    # 验证配置
    try:
        validate_config(config)
    except ValueError as e:
        print(f"配置验证失败: {e}")
        return

    print(f"\n{'='*80}")
    print("自定义配置测试")
    print(f"{'='*80}")
    print(f"配置文件: {CONFIG_FILE}")
    print()

    # 检查是否是批量测试模式
    is_batch_mode = False
    batch_param = None
    batch_values = []

    # 检查concurrent是否为数组
    if 'concurrent' in config and isinstance(config['concurrent'], list) and len(config['concurrent']) > 1:
        is_batch_mode = True
        batch_param = 'concurrent'
        batch_values = config['concurrent']
    # 检查total是否为数组
    elif 'total' in config and isinstance(config['total'], list) and len(config['total']) > 1:
        is_batch_mode = True
        batch_param = 'total'
        batch_values = config['total']
    # 检查duration是否为数组
    elif 'duration' in config and isinstance(config['duration'], list) and len(config['duration']) > 1:
        is_batch_mode = True
        batch_param = 'duration'
        batch_values = config['duration']

    # 准备基础配置
    base_config = {
        'url': config['url'],
        'timeout': config.get('timeout', 5),
        't1': config.get('t1', 1.0),
        't2': config.get('t2', 3.0),
        'content': config.get('content', ''),
    }

    # 输出目录
    output_dir = config.get('output_dir', 'test/load_test/reports')
    # 对于自定义配置测试，使用 custom 子文件夹
    output_dir = os.path.join(output_dir, 'custom')
    save_json = config.get('json', False)
    cooldown = config.get('batch_mode', {}).get('cooldown', 5)

    try:
        if is_batch_mode:
            # 批量测试模式
            print(f"批量测试模式")
            print(f"批量参数: {batch_param}")
            print(f"参数值: {batch_values}")
            print(f"测试数量: {len(batch_values)}")
            print(f"输出目录: {output_dir}")
            print()

            # 准备测试配置列表
            test_configs = []

            for param_value in batch_values:
                test_config = {}

                if batch_param == 'concurrent':
                    test_config['concurrent'] = param_value
                    # 检查total和duration
                    if 'total' in config and not isinstance(config['total'], list):
                        test_config['total'] = config['total']
                    elif 'duration' in config and not isinstance(config['duration'], list):
                        test_config['duration'] = config['duration']
                    else:
                        test_config['total'] = 500  # 默认值

                elif batch_param == 'total':
                    test_config['total'] = param_value
                    test_config['concurrent'] = config.get('concurrent', [10])[0] if isinstance(config.get('concurrent'), list) else config.get('concurrent', 10)

                elif batch_param == 'duration':
                    test_config['duration'] = param_value
                    test_config['concurrent'] = config.get('concurrent', [10])[0] if isinstance(config.get('concurrent'), list) else config.get('concurrent', 10)

                test_configs.append(test_config)

            # 运行批量测试
            results = await run_sequential_tests(
                test_configs=test_configs,
                base_config=base_config,
                output_dir=output_dir,
                save_json=save_json,
                cooldown=cooldown,
                generate_summary=True
            )

        else:
            # 单次测试模式
            concurrent = config.get('concurrent', 10)
            total = config.get('total')
            duration = config.get('duration')

            print(f"单次测试模式")
            print(f"并发数: {concurrent}")
            if total:
                print(f"总请求数: {total}")
            if duration:
                print(f"持续时间: {duration}秒")
            print(f"输出目录: {output_dir}")
            print()

            result = await run_single_test(
                url=base_config['url'],
                concurrent=concurrent,
                total=total,
                duration=duration,
                payload={"Content": base_config['content']},
                timeout=base_config['timeout'],
                t1=base_config['t1'],
                t2=base_config['t2'],
                output_dir=output_dir,
                save_json=save_json,
                test_name="custom_test"
            )

            # 打印结果摘要
            stats = result.get_statistics()
            print(f"\n{'='*80}")
            print("测试完成！")
            print(f"{'='*80}")
            print(f"QPS: {stats.get('qps', 0):.2f}")
            print(f"Fast率: {stats.get('fast_rate', 0):.2f}%")
            print(f"Slow率: {stats.get('slow_rate', 0):.2f}%")
            print(f"Bad率: {stats.get('bad_rate', 0):.2f}%")

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n\n测试出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
