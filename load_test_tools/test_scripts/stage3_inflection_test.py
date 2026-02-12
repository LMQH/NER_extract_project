#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段3: 拐点验证测试
目标: 精确定位拐点，在拐点附近精细测试
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

# 阶段3特定配置: 在拐点附近精细测试
# 假设从阶段2发现拐点在并发50附近
INFLECTION_POINT = 50
TEST_RANGE = 20
STEP = 5
TOTAL_PER_TEST = 500

TEST_CONFIGS = [
    {
        'concurrent': concurrent,
        'total': TOTAL_PER_TEST
    }
    for concurrent in range(
        INFLECTION_POINT - TEST_RANGE,
        INFLECTION_POINT + TEST_RANGE + 1,
        STEP
    )
]
# 结果: 并发30, 35, 40, 45, 50, 55, 60, 65, 70

# 从配置文件加载输出配置
output_config = get_output_config(CONFIG_FILE)
OUTPUT_DIR = os.path.join(output_config['output_dir'], 'stage3')
SAVE_JSON = output_config['json']
COOLDOWN = output_config['cooldown']

# =========================================================

async def main():
    """主函数"""
    print(f"\n{'='*80}")
    print("阶段3: 拐点验证测试")
    print(f"{'='*80}")
    print(f"测试目标: 精确定位拐点，在拐点附近精细测试")
    print(f"测试配置数: {len(TEST_CONFIGS)}")
    print(f"并发范围: {INFLECTION_POINT - TEST_RANGE} -> {INFLECTION_POINT + TEST_RANGE} (步进{STEP})")
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
        print("阶段3测试完成！")
        print(f"{'='*80}")

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n\n测试出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
