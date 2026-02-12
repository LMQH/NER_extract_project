"""
MGeo地理组成分析模型调用模块
使用ModelScope的MGeo地理组成分析模型进行地理实体抽取和分析
支持地理组成分析、地理实体识别等任务
"""
import os
from pathlib import Path
from typing import Dict, Any
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from .base_model import BaseModel
from ..utils.logger import get_logger
from ..utils.exceptions import ModelLoadError

logger = get_logger(__name__)


class MGeoModel(BaseModel):
    """MGeo地理组成分析模型封装类，支持地理组成分析任务"""

    def __init__(self, model_path: str):
        """
        初始化MGeo地理组成分析模型

        Args:
            ModelPath: 模型路径
        """
        super().__init__(model_path)
        self.pipeline = None

        # 检查模型路径是否存在
        model_abs_path = Path(model_path)
        if not model_abs_path.exists():
            error_msg = (
                f"本地模型路径不存在: {model_path}。"
                f"请检查模型文件是否已下载。"
            )
            logger.error(error_msg)
            raise ModelLoadError(error_msg)

    def load(self):
        """加载模型"""
        try:
            # MGeo模型使用token-classification任务
            task_type = Tasks.token_classification

            # 检查transformers版本兼容性
            try:
                import transformers
                major, minor = map(int, transformers.__version__.split('.')[:2])
                logger.debug(f"transformers版本: {transformers.__version__}")
            except Exception:
                pass

            # 使用本地路径加载模型
            logger.info(f"正在加载MGeo模型: {self.model_path}")
            self.pipeline = pipeline(
                task_type,
                self.model_path,
                model_revision='master'
            )
            logger.info("MGeo模型加载成功")

        except Exception as e:
            error_msg = f"模型加载失败: {str(e)}"
            logger.error(error_msg)
            raise ModelLoadError(error_msg)

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        从文本中抽取地理实体（支持地理组成分析任务）

        Args:
            text: 输入文本（地址query，如"浙江省杭州市余杭区阿里巴巴西溪园区"）

        Returns:
            抽取结果字典，包含:
            - text: 原始文本
            - entities: 抽取的实体结果，格式为:
              {
                "output": [
                  {"type": "PB", "start": 0, "end": 3, "span": "浙江省"},
                  {"type": "PC", "start": 3, "end": 6, "span": "杭州市"},
                  ...
                ]
              }
            - error: 错误信息（如果有）

        示例:
            result = model.extract_entities(
                text='浙江省杭州市余杭区阿里巴巴西溪园区'
            )

            输出示例:
            {
              "text": "浙江省杭州市余杭区阿里巴巴西溪园区",
              "entities": {
                "output": [
                  {"type": "PB", "start": 0, "end": 3, "span": "浙江省"},
                  {"type": "PC", "start": 3, "end": 6, "span": "杭州市"},
                  {"type": "PD", "start": 6, "end": 9, "span": "余杭区"},
                  {"type": "Entity", "start": 9, "end": 17, "span": "阿里巴巴西溪园区"}
                ]
              }
            }
        """
        if not text or not text.strip():
            return {"text": text, "entities": {}}

        # 确保模型已加载
        if not self.pipeline:
            self.load()

        try:
            # MGeo模型使用token-classification任务，只需要input参数
            result = self.pipeline(input=text)

            # 将numpy类型转换为Python原生类型（解决Pydantic序列化问题）
            def convert_numpy_types(obj):
                """递归转换numpy类型为Python原生类型"""
                import numpy as np
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {key: convert_numpy_types(value) for key, value in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [convert_numpy_types(item) for item in obj]
                else:
                    return obj

            # 转换结果中的numpy类型
            result = convert_numpy_types(result)

            # 确保返回格式一致
            if result and isinstance(result, dict):
                return {
                    "text": text,
                    "entities": result
                }
            else:
                return {
                    "text": text,
                    "entities": {"output": result} if result else {}
                }

        except Exception as e:
            error_msg = f"实体抽取出错: {str(e)}"
            logger.error(error_msg)
            return {
                "text": text,
                "entities": {},
                "error": error_msg
            }
