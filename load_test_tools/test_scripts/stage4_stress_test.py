#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段4: 极限压力测试
目标: 观察系统极限行为，超过拐点2-3倍压力
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
from core.load_test_runner import run_sequential_tests
from core.load_test_config import get_base_config, get_output_config

# ==================== 测试配置（从配置文件加载） ====================
# 获取配置文件路径
script_dir = os.path.dirname(os.path.abspath(__file__))
load_test_dir = os.path.abspath(os.path.join(script_dir, '..'))
CONFIG_FILE = os.path.join(load_test_dir, 'load_test_config.json')

# 从配置文件加载基础配置
BASE_CONFIG = get_base_config(CONFIG_FILE)

# 阶段4特定配置: 超过拐点2-3倍压力
# 假设拐点为50
INFLECTION_POINT = 50
DURATION = 120  # 2分钟

TEST_CONFIGS = [
    {'concurrent': int(INFLECTION_POINT * 2.5), 'duration': DURATION},
    {'concurrent': int(INFLECTION_POINT * 3.0), 'duration': DURATION},
]
# 结果: 并发125持续2分钟，并发150持续2分钟

# 从配置文件加载输出配置
output_config = get_output_config(CONFIG_FILE)
OUTPUT_DIR = os.path.join(output_config['output_dir'], 'stage4')
SAVE_JSON = output_config['json']
COOLDOWN = output_config['cooldown']

# =========================================================

async def main():
    """主函数"""
    print(f"\n{'='*80}")
    print("阶段4: 极限压力测试")
    print(f"{'='*80}")
    print(f"测试目标: 观察系统极限行为，超过拐点2-3倍压力")
    print(f"测试配置数: {len(TEST_CONFIGS)}")
    print(f"并发级别: {[c['concurrent'] for c in TEST_CONFIGS]}")
    print(f"输出目录: {OUTPUT_DIR}")
    print()

    try:
        results = await run_sequential_tests(
            test_configs=TEST_CONFIGS,
            base_config=BASE_CONFIG,
            output_dir=OUTPUT_DIR,
            save_json=SAVE_JSON,
            cooldown=COOLDOWN,
            generate_summary=True
        )

        print(f"\n{'='*80}")
        print("阶段4测试完成！")
        print(f"{'='*80}")

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n\n测试出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
