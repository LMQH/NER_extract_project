"""
NumPy类型转换工具
"""
from typing import Any, Dict, List
import numpy as np


def convert_numpy_types(obj: Any) -> Any:
    """
    递归转换numpy类型为Python原生类型

    Args:
        obj: 待转换的对象

    Returns:
        转换后的对象
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj
