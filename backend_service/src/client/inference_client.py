"""
推理服务HTTP客户端
负责与推理服务通信，包含重试机制和错误处理
"""
import os
import logging
import time
from typing import Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ...utils.logger import get_logger

logger = get_logger("Backend_Client")


class InferenceClient:
    """推理服务客户端"""

    def __init__(self):
        """初始化客户端"""
        self.base_url = os.getenv('INFERENCE_SERVICE_URL', 'http://localhost:14467')
        self.timeout = float(os.getenv('INFERENCE_TIMEOUT', '30.0'))
        self.max_retries = int(os.getenv('INFERENCE_MAX_RETRIES', '3'))

        # 创建httpx客户端
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout
        )

        logger.info(f"推理服务客户端初始化成功 | URL: {self.base_url} | 超时: {self.timeout}s")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def extract_entities_async(self, content: str, model_name: str = None) -> Dict[str, Any]:
        """
        调用推理服务进行实体抽取（异步版本）

        Args:
            content: 待处理文本
            model_name: 模型名称

        Returns:
            推理结果字典
        """
        if model_name is None:
            model_name = 'mgeo_geographic_composition_analysis_chinese_base'

        request_data = {
            "Content": content,
            "model_name": model_name
        }

        try:
            logger.debug(f"发送推理请求: {content[:50]}...")

            response = await self.client.post(
                "/inference/extract",
                json=request_data
            )
            response.raise_for_status()

            result = response.json()
            logger.info(f"推理调用成功 | 耗时: {result.get('inference_time', 0):.4f}秒")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"推理服务HTTP错误: {e.response.status_code} | {e.response.text}")
            raise
        except httpx.TimeoutException:
            logger.error(f"推理服务超时: {self.timeout}秒")
            raise
        except Exception as e:
            logger.error(f"推理服务调用失败: {str(e)}")
            raise

    def extract_entities(self, content: str, model_name: str = None) -> Dict[str, Any]:
        """
        调用推理服务进行实体抽取（同步版本）

        Args:
            content: 待处理文本
            model_name: 模型名称

        Returns:
            推理结果字典
        """
        if model_name is None:
            model_name = 'mgeo_geographic_composition_analysis_chinese_base'

        request_data = {
            "Content": content,
            "model_name": model_name
        }

        try:
            logger.debug(f"发送推理请求: {content[:50]}...")

            response = self.client.post(
                "/inference/extract",
                json=request_data
            )
            response.raise_for_status()

            result = response.json()
            logger.info(f"推理调用成功 | 耗时: {result.get('inference_time', 0):.4f}秒")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"推理服务HTTP错误: {e.response.status_code} | {e.response.text}")
            raise
        except httpx.TimeoutException:
            logger.error(f"推理服务超时: {self.timeout}秒")
            raise
        except Exception as e:
            logger.error(f"推理服务调用失败: {str(e)}")
            raise

    async def health_check_async(self) -> bool:
        """健康检查（异步版本）"""
        try:
            response = await self.client.get("/inference/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"推理服务健康检查失败: {str(e)}")
            return False

    def health_check(self) -> bool:
        """健康检查（同步版本）"""
        try:
            response = self.client.get("/inference/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"推理服务健康检查失败: {str(e)}")
            return False

    async def list_models_async(self) -> Dict[str, Any]:
        """获取模型列表（异步版本）"""
        try:
            response = await self.client.get("/inference/models")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取模型列表失败: {str(e)}")
            raise

    def list_models(self) -> Dict[str, Any]:
        """获取模型列表（同步版本）"""
        try:
            response = self.client.get("/inference/models")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取模型列表失败: {str(e)}")
            raise

    def close(self):
        """关闭客户端"""
        try:
            self.client.close()
            logger.info("推理服务客户端已关闭")
        except Exception as e:
            logger.warning(f"关闭客户端时出错: {str(e)}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
