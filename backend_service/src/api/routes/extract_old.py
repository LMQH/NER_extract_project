"""
实体抽取相关路由
"""
import os
import time
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from src.api.schemas import ExtractRequest, ExtractResponse
from src.processor_mgeo.converters import convert_mgeo_to_output_format
from src.processor_mgeo.input_validator import InputValidator
from src.api.dependencies import get_model_manager, get_config_manager, get_address_completer
from src.database.api_usage_counter import ApiUsageCounter
from src.database.api_error_logger import ApiErrorLogger

router = APIRouter()
logger = logging.getLogger("NER_API")

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
    model_manager=Depends(get_model_manager),
    config_manager=Depends(get_config_manager),
    address_completer=Depends(get_address_completer)
):
    """
    实体抽取接口
    
    状态码说明（按优先级从高到低）：
    - 100: 解析成功
    - 101: 接口请求参数错误（Content字段为空，所有后续流程都无法执行）
    - 102: 地理模型解析失败（模型处理失败、模型加载失败、地址信息无法解析，103有关的流程也无法完成）
    - 103: 地址无法完全确定（地址信息缺失或存在多个候选值无法确定）
    """
    """
    实体抽取接口
    
    从文本中抽取实体，使用 mgeo_geographic_composition_analysis_chinese_base 模型。
    
    请求格式：
    {
        "Content": "广东省深圳市龙岗区坂田街道长坑路西2巷2号202 黄大大 18273778575"
    }
    
    响应格式（mgeo_geographic_composition_analysis_chinese_base模型）：
    {
        "EBusinessID": "1279441",  # 可通过环境变量EBUSINESS_ID配置
        "Data": {
            "ProvinceName": {
                "id": 1000,
                "parent_id": null,
                "region_name": "广东省",
                "region_type": "province",
                "region_code": "440000",
                "region_full_name": "广东省",
                "region_short_name": "广东"
            },
            "CityName": {
                "id": 1001,
                "parent_id": 1000,
                "region_name": "深圳市",
                "region_type": "city",
                "region_code": "440300",
                "region_full_name": "广东省深圳市",
                "region_short_name": "深圳"
            },
            "ExpAreaName": {
                "id": 1002,
                "parent_id": 1001,
                "region_name": "龙岗区",
                "region_type": "area",
                "region_code": "440307",
                "region_full_name": "广东省深圳市龙岗区",
                "region_short_name": "龙岗"
            },
            "StreetName": {
                "id": 1003,
                "parent_id": 1002,
                "region_name": "坂田街道",
                "region_type": "street",
                "region_code": "440307001",
                "region_full_name": "广东省深圳市龙岗区坂田街道",
                "region_short_name": "坂田"
            },
            "AreasInfo": "长坑路",
            "Address": "长坑路西2巷2号202",
            "others": "",
            "Mobile": "18273778575",
            "Name": "黄大大"
        },
        "Success": true,
        "Reason": "解析成功",
        "ResultCode": "100",
        "Warning": []
    }
    """
    try:
        # API使用统计：增加总计数（不影响接口功能，失败只记录日志）
        try:
            _api_usage_counter.increment_api_count("/api/extract")
        except Exception as e:
            logger.warning(f"API使用统计总计数失败（不影响接口功能）: {str(e)}")
        
        # 验证输入（请求参数错误 -> 101，最高优先级）
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
        
        # 检测Content字段中的危险字符（防止SQL注入等安全风险）
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
        
        # 固定使用 mgeo_geographic_composition_analysis_chinese_base 模型
        model_name = 'mgeo_geographic_composition_analysis_chinese_base'
        
        # 加载模型
        try:
            model = model_manager.load_model(model_name)
        except Exception as e:
            # 模型加载失败，返回102状态码（地理模型解析失败）
            error_response = ExtractResponse(
                EBusinessID=EBusinessID,
                Data={},
                Success=False,
                Reason=f"模型加载失败: {str(e)}",
                ResultCode="102",
                Warning=[]
            )
            logger.error(f"模型加载失败，返回状态码102: {str(e)}")
            _log_error_if_needed(error_response, request.Content)
            return error_response
        
        # 执行实体抽取
        # 记录推理开始时间
        inference_start_time = time.time()
        try:
            result = model.extract_entities(request.Content)
            
            # 记录推理结束时间并计算耗时
            inference_end_time = time.time()
            inference_duration = inference_end_time - inference_start_time
            
            # 记录推理时间到日志
            logger.info(f"Mgeo模型推理耗时: {inference_duration:.4f}秒 ({inference_duration*1000:.2f}毫秒)")
            
            # mgeo地理组成分析模型需要转换为规定格式
            formatted_result = convert_mgeo_to_output_format(result, request.Content)
            
            # 数据校验和清洗：在格式转换之后、地址补全之前进行
            # 确保进入数据库匹配阶段的数据是干净、安全的
            formatted_result = InputValidator.validate_extract_response(formatted_result)
            
            # 检查模型返回的结果，如果模型处理失败，设置102状态码（地理模型解析失败）
            # 优先级检查：101（请求参数错误）> 102（地理模型解析失败）> 103（地址无法完全确定）
            if not formatted_result.get('Success', True):
                result_code = formatted_result.get('ResultCode', '102')
                # 如果已经是101（请求参数错误），保持原样，因为101优先级最高
                if result_code == '101':
                    logger.warning(f"模型返回请求参数错误，状态码: {result_code}, 原因: {formatted_result.get('Reason', '未知错误')}")
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
                    logger.warning(f"模型处理失败，状态码: {result_code}, 原因: {formatted_result.get('Reason', '未知错误')}")
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
                    # 其他错误，统一设置为102（地理模型解析失败）
                    formatted_result['ResultCode'] = '102'
                    formatted_result['Success'] = False
                    formatted_result['Reason'] = formatted_result.get('Reason', '模型处理失败')
                    logger.warning(f"模型处理失败，设置状态码102: {formatted_result.get('Reason', '未知错误')}")
                    # 转换为ExtractResponse并记录错误日志
                    error_response = ExtractResponse(
                        EBusinessID=EBusinessID,
                        Data=formatted_result.get('Data', {}),
                        Success=formatted_result.get('Success', False),
                        Reason=formatted_result.get('Reason', '模型处理失败'),
                        ResultCode='102',
                        Warning=formatted_result.get('Warning', [])
                    )
                    _log_error_if_needed(error_response, request.Content)
                    return error_response
            
            # 进行地址补全
            if address_completer:
                try:
                    formatted_result = address_completer.complete_extract_response(formatted_result)
                    # 优先级检查：如果地址补全返回了101（请求参数错误），保持原样
                    # 如果返回了102（地理模型解析失败），保持原样
                    # 如果返回了103（地址无法完全确定），保持原样
                    # 如果返回了100（成功），保持原样
                except Exception as e:
                    logger.warning(f"地址补全失败，返回原始结果: {str(e)}")
                    # 地址补全失败，设置102状态码（地理模型解析失败）
                    # 但需要检查优先级：如果已经有101，不应该被覆盖
                    current_code = formatted_result.get('ResultCode', '102')
                    if current_code != '101':
                        formatted_result['ResultCode'] = '102'
                        formatted_result['Success'] = False
                        formatted_result['Reason'] = f'地址补全失败: {str(e)}'
            
            # 转换为ExtractResponse对象并返回
            # 如果失败则记录错误日志
            response = ExtractResponse(
                EBusinessID=EBusinessID,
                Data=formatted_result.get('Data', {}),
                Success=formatted_result.get('Success', True),
                Reason=formatted_result.get('Reason', '解析成功'),
                ResultCode=formatted_result.get('ResultCode', '100'),
                Warning=formatted_result.get('Warning', [])
            )
            
            # 如果失败，记录错误日志
            if not response.Success or response.ResultCode != "100":
                _log_error_if_needed(response, request.Content)
            else:
                # 成功时，增加成功计数（不影响接口功能，失败只记录日志）
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
            logger.error(f"Mgeo模型推理耗时: {inference_duration:.4f}秒 ({inference_duration*1000:.2f}毫秒) | 错误: {str(e)}")
            # 模型处理失败，返回102状态码（地理模型解析失败）
            # 注意：这里使用全局导入的ExtractResponse，不进行局部导入以避免变量作用域冲突
            error_response = ExtractResponse(
                EBusinessID=EBusinessID,
                Data={},
                Success=False,
                Reason=f"实体抽取失败: {str(e)}",
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
    model_manager=Depends(get_model_manager)
) -> Dict[str, Any]:
    """
    模型测试接口 - 直接返回模型原始输出
    
    该接口与 /api/extract 使用相同的输入格式，但直接返回模型本身的原始输出，
    不进行任何格式转换、地址补全等后处理。
    
    请求格式：
    {
        "Content": "广东省深圳市龙岗区坂田街道长坑路西2巷2号202 黄大大 18273778575"
    }
    
    响应格式：直接返回模型原始输出
    """
    try:
        # 验证输入
        if not request.Content or not request.Content.strip():
            raise HTTPException(status_code=400, detail="Content字段不能为空")
        
        # 固定使用 mgeo_geographic_composition_analysis_chinese_base 模型
        model_name = 'mgeo_geographic_composition_analysis_chinese_base'
        
        # 加载模型
        try:
            model = model_manager.load_model(model_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"模型加载失败: {str(e)}")
        
        # 直接调用模型，返回原始输出
        try:
            result = model.extract_entities(request.Content)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"模型处理失败: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

