"""
推理服务路由模块
"""
from fastapi import APIRouter
from . import inference, system

__all__ = ['inference', 'system']
