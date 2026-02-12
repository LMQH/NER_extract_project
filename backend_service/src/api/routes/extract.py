"""
实体抽取相关路由（重构版）
通过HTTP调用推理服务，而非本地模型加载
"""
import os
import time
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from src.api.schemas import ExtractRequest, ExtractResponse
from src.processor_mgeo.converters import convert_mgeo_to_output_format
from src.processor_mgeo.input_validator import InputValidator
from src.api.dependencies import get_inference_client, get_config_manager, get_address_completer
from src.database.api_usage_counter import ApiUsageCounter
from src.database.api_error_logger import ApiErrorLogger

router = APIRouter()
logger = logging.getLogger("Backend_API")

# EBusinessID配置：从环境变量读取，如果没有则使用默认值
EBusinessID = os.getenv("EBUSINESS_ID", "2223333")

# 初始化API使用统计计数器和错误日志记录器（模块级单例）
_api_usage_counter = ApiUsageCounter()
_api_error_logger = None  # 延迟初始化，使用独立的统计数据库


def _get_error_logger():
    """获取错误日志记录器（延迟初始化，使用独立的统计数据库）"""
    global _api_error_logger
    if _api_error_logger is None:
        try:
            # 使用独立的统计数据库连接
            _api_error_logger = ApiErrorLogger()
        except Exception as e:
            # 初始化失败，记录日志但不影响接口功能
            logger.warning(f"初始化错误日志记录器失败（不影响接口功能）: {str(e)}")
            # 创建一个禁用状态的错误日志记录器
            _api_error_logger = ApiErrorLogger()
            _api_error_logger.enabled = False
    return _api_error_logger


def _log_error_if_needed(response: ExtractResponse, content: str):
    """如果响应失败，记录错误日志"""
    try:
        if not response.Success or response.ResultCode != "100":
            error_logger = _get_error_logger()
            if error_logger:
                # 将响应转换为字典格式
                response_dict = {
                    'Data': response.Data,
                    'Warning': response.Warning,
                    'Success': response.Success,
                    'Reason': response.Reason,
                    'ResultCode': response.ResultCode
                }
                error_logger.log_api_error_from_response(
                    content=content,
                    response_data=response_dict,
                    model_type='mgeo_geographic_composition_analysis_chinese_base'
                )
    except Exception as e:
        # 记录错误但不影响接口响应
        logger.warning(f"记录错误日志失败: {str(e)}")


@router.post("/api/extract", response_model=ExtractResponse, tags=["实体抽取"])
async def extract_entities(
    request: ExtractRequest,
    inference_client=Depends(get_inference_client),
    config_manager=Depends(get_config_manager),
    address_completer=Depends(get_address_completer)
):
    """
    实体抽取接口（重构版）

    变更说明:
    1. 移除本地模型加载，改为HTTP调用推理服务
    2. 保持地址补全逻辑不变
    3. 保持统计和错误日志功能不变
    4. 保持原有的响应格式和状态码逻辑
    """
    try:
        # API使用统计: 总计数
        try:
            _api_usage_counter.increment_api_count("/api/extract")
        except Exception as e:
            logger.warning(f"API使用统计失败（不影响接口功能）: {str(e)}")

        # 1. 输入验证（请求参数错误 -> 101，最高优先级）
        if not request.Content or not request.Content.strip():
            error_response = ExtractResponse(
                EBusinessID=EBusinessID,
                Data={},
                Success=False,
                Reason="Content字段不能为空",
                ResultCode="101",
                Warning=[]
            )
            logger.warning("请求参数错误: Content字段不能为空，返回状态码101")
            _log_error_if_needed(error_response, request.Content or "")
            return error_response

        # 2. 危险字符检测（防止SQL注入等安全风险）
        if InputValidator._contains_dangerous_pattern(request.Content):
            error_response = ExtractResponse(
                EBusinessID=EBusinessID,
                Data={},
                Success=False,
                Reason="Content字段包含危险字符，可能存在安全风险",
                ResultCode="101",
                Warning=[]
            )
            logger.error(f"请求参数错误: Content字段包含危险字符: {request.Content}，返回状态码101")
            _log_error_if_needed(error_response, request.Content)
            return error_response

        # 3. 调用推理服务进行实体抽取（重构：使用HTTP客户端）
        inference_start_time = time.time()
        try:
            # 推理服务会返回包含entities和text的结果
            inference_result = inference_client.extract_entities(request.Content)

            # 推理服务返回格式: {"text": ..., "entities": {...}, "inference_time": ..., "success": ..., "error": ...}
            # 需要将entities转换为模型期望的格式: {"entities": {"output": [...]}}

            # 构造符合convert_mgeo_to_output_format期望的格式
            model_result = {
                "text": inference_result.get("text", request.Content),
                "entities": inference_result.get("entities", {})
            }

            # 记录推理结束时间并计算耗时
            inference_end_time = time.time()
            inference_duration = inference_end_time - inference_start_time

            # 记录推理时间到日志
            logger.info(f"推理服务调用耗时: {inference_duration:.4f}秒 ({inference_duration*1000:.2f}毫秒)")

            # mgeo地理组成分析模型需要转换为规定格式
            formatted_result = convert_mgeo_to_output_format(model_result, request.Content)

            # 数据校验和清洗：在格式转换之后、地址补全之前进行
            # 确保进入数据库匹配阶段的数据是干净、安全的
            formatted_result = InputValidator.validate_extract_response(formatted_result)

            # 检查推理结果状态，如果推理服务调用失败，设置102状态码
            # 优先级检查：101（请求参数错误）> 102（推理服务调用失败）> 103（地址无法完全确定）
            if not formatted_result.get('Success', True):
                result_code = formatted_result.get('ResultCode', '102')
                # 如果已经是101（请求参数错误），保持原样，因为101优先级最高
                if result_code == '101':
                    logger.warning(f"推理返回请求参数错误，状态码: {result_code}, 原因: {formatted_result.get('Reason', '未知错误')}")
                    # 转换为ExtractResponse并记录错误日志
                    error_response = ExtractResponse(
                        EBusinessID=EBusinessID,
                        Data=formatted_result.get('Data', {}),
                        Success=formatted_result.get('Success', False),
                        Reason=formatted_result.get('Reason', '未知错误'),
                        ResultCode=formatted_result.get('ResultCode', '101'),
                        Warning=formatted_result.get('Warning', [])
                    )
                    _log_error_if_needed(error_response, request.Content)
                    return error_response
                # 如果是102或103，保持原样
                elif result_code in ['102', '103']:
                    logger.warning(f"推理服务调用失败，状态码: {result_code}, 原因: {formatted_result.get('Reason', '未知错误')}")
                    # 转换为ExtractResponse并记录错误日志
                    error_response = ExtractResponse(
                        EBusinessID=EBusinessID,
                        Data=formatted_result.get('Data', {}),
                        Success=formatted_result.get('Success', False),
                        Reason=formatted_result.get('Reason', '未知错误'),
                        ResultCode=formatted_result.get('ResultCode', '102'),
                        Warning=formatted_result.get('Warning', [])
                    )
                    _log_error_if_needed(error_response, request.Content)
                    return error_response
                else:
                    # 其他错误，统一设置为102（推理服务调用失败）
                    formatted_result['ResultCode'] = '102'
                    formatted_result['Success'] = False
                    formatted_result['Reason'] = formatted_result.get('Reason', '推理服务调用失败')
                    logger.warning(f"推理服务调用失败，设置状态码102: {formatted_result.get('Reason', '未知错误')}")
                    # 转换为ExtractResponse并记录错误日志
                    error_response = ExtractResponse(
                        EBusinessID=EBusinessID,
                        Data=formatted_result.get('Data', {}),
                        Success=formatted_result.get('Success', False),
                        Reason=formatted_result.get('Reason', '推理服务调用失败'),
                        ResultCode='102',
                        Warning=formatted_result.get('Warning', [])
                    )
                    _log_error_if_needed(error_response, request.Content)
                    return error_response

            # 进行地址补全（保持不变）
            if address_completer:
                try:
                    formatted_result = address_completer.complete_extract_response(formatted_result)
                    # 优先级检查：如果已经有101或102，不应该被103覆盖
                    current_code = formatted_result.get('ResultCode', '102')
                    if current_code in ['101', '102']:
                        # 保持原有的高优先级状态码
                        result_code = current_code
                        logger.info(f"保持高优先级状态码 {result_code}，不设置103")
                    else:
                        # 使用地址补全返回的状态码
                        result_code = formatted_result.get('ResultCode', '102')
                        # 地址补全可能返回103（地址无法完全确定）
                        logger.debug(f"地址补全返回状态码: {result_code}")
                except Exception as e:
                    logger.warning(f"地址补全失败，返回原始结果: {str(e)}")
                    # 地址补全失败，设置102状态码（推理服务调用失败）
                    # 但需要检查优先级：如果已经有101，不应该被覆盖
                    current_code = formatted_result.get('ResultCode', '102')
                    if current_code != '101':
                        formatted_result['ResultCode'] = '102'
                        formatted_result['Success'] = False
                        formatted_result['Reason'] = f'地址补全失败: {str(e)}'

            # 转换为ExtractResponse对象并返回
            response = ExtractResponse(
                EBusinessID=EBusinessID,
                Data=formatted_result.get('Data', {}),
                Success=formatted_result.get('Success', True),
                Reason=formatted_result.get('Reason', '解析成功'),
                ResultCode=formatted_result.get('ResultCode', '100'),
                Warning=formatted_result.get('Warning', [])
            )

            # 如果失败则记录错误日志
            if not response.Success or response.ResultCode != "100":
                _log_error_if_needed(response, request.Content)
            else:
                # 成功时，增加成功计数
                try:
                    _api_usage_counter.increment_api_count("/api/extract", success=True)
                except Exception as e:
                    logger.warning(f"API使用统计成功计数失败（不影响接口功能）: {str(e)}")

            return response

        except Exception as e:
            # 记录推理结束时间并计算耗时（即使失败也记录）
            inference_end_time = time.time()
            inference_duration = inference_end_time - inference_start_time

            # 记录推理时间到日志（失败情况）
            logger.error(f"推理服务调用耗时: {inference_duration:.4f}秒 ({inference_duration*1000:.2f}毫秒) | 错误: {str(e)}")

            # 推理服务调用失败，返回102状态码（推理服务调用失败）
            # 注意：这里使用全局导入的ExtractResponse，不进行局部导入以避免变量作用域冲突
            error_response = ExtractResponse(
                EBusinessID=EBusinessID,
                Data={},
                Success=False,
                Reason=f"推理服务调用失败: {str(e)}",
                ResultCode="102",
                Warning=[]
            )
            _log_error_if_needed(error_response, request.Content)
            return error_response

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.post("/api/test-model", tags=["模型测试"])
async def test_model(
    request: ExtractRequest,
    inference_client=Depends(get_inference_client)
) -> Dict[str, Any]:
    """
    模型测试接口（重构版）
    直接调用推理服务并返回原始输出

    该接口与 /api/extract 使用相同的输入格式，但直接返回推理服务的原始输出，
    不进行任何格式转换、地址补全等后处理。
    """
    try:
        # 验证输入
        if not request.Content or not request.Content.strip():
            raise HTTPException(status_code=400, detail="Content字段不能为空")

        # 直接调用推理服务
        try:
            result = inference_client.extract_entities(request.Content)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"推理服务调用失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")
