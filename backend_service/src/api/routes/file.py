"""
文件管理相关路由
已废弃：不再支持文件上传功能，所有文件通过API直接传递内容
"""
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/api/upload", tags=["文件管理"])
async def upload_file():
    """
    文件上传接口（已废弃）
    
    此接口已废弃，请使用实体抽取接口直接传递文本内容。
    """
    raise HTTPException(
        status_code=410,
        detail="文件上传接口已废弃。请使用 /api/extract 接口，通过 Content 字段直接传递文本内容。"
    )


@router.post("/api/upload/multiple", tags=["文件管理"])
async def upload_multiple_files():
    """
    多文件上传接口（已废弃）
    
    此接口已废弃，请使用实体抽取接口直接传递文本内容。
    """
    raise HTTPException(
        status_code=410,
        detail="多文件上传接口已废弃。请使用 /api/extract 接口，通过 Content 字段直接传递文本内容。"
    )

