"""
MiniMax MCP (Model Context Protocol) 客户端模块

基于原项目 minimax_mcp_v2_label_materials.py 和 
minimax_mcp_multimodal_label_materials.py 的独立实现。

提供：
1. MCP协议的图片理解功能（understand_image tool call）
2. 视频音频提取（ffmpeg）
3. Whisper语音转文字（可选）
4. 多模态素材处理流程

特点：
- 完全独立运行，无外部依赖
- 支持MCP和直连两种模式自动降级
- 完善的错误处理和日志记录
- 与现有labeler.py无缝集成
"""
import os
import json
import base64
import uuid
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
from io import BytesIO

import httpx
from PIL import Image
from loguru import logger


class MiniMaxMCPClient:
    """
    MiniMax MCP协议客户端
    
    实现MiniMax的MCP (Model Context Protocol) 调用，
    主要用于视觉AI打标任务。
    
    支持两种模式：
    1. MCP模式：通过tool_call机制调用understand_image工具
    2. 直连模式：直接发送图片到视觉API（MCP不可用时自动降级）
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "MiniMax-M2.7",
        base_url: str = "https://api.minimaxi.com/v1",
        use_mcp: bool = True,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        timeout: int = 120,
        image_max_size: int = 1024,
        image_quality: int = 85,
    ):
        """
        初始化MCP客户端
        
        Args:
            api_key: MiniMax API密钥
            model: 模型名称（默认MiniMax-M2.7）
            base_url: API基础URL
            use_mcp: 是否使用MCP协议（默认True，失败时自动降级）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            timeout: 请求超时（秒）
            image_max_size: 图片最大边长（像素）
            image_quality: JPEG压缩质量（1-100）
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.use_mcp = use_mcp
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.image_max_size = image_max_size
        self.image_quality = image_quality
        
        # MCP工具定义
        self._mcp_tools = self._build_mcp_tools()
        
        # 统计信息
        self._stats = {
            "total_calls": 0,
            "mcp_calls": 0,
            "direct_calls": 0,
            "success_count": 0,
            "fail_count": 0,
        }
        
        logger.info(
            f"🔌 MiniMax MCP客户端初始化 | "
            f"模型: {self.model} | "
            f"MCP模式: {'启用' if self.use_mcp else '禁用'} | "
            f"Base URL: {self.base_url}"
        )
    
    def _build_mcp_tools(self) -> List[Dict]:
        """
        构建MCP工具定义
        
        基于原项目minimax_mcp_v2_label_materials.py的实现，
        定义understand_image工具用于图片理解。
        
        Returns:
            List[Dict]: OpenAI格式的工具定义列表
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "understand_image",
                    "description": "理解图片内容并返回详细的分析结果，包括场景描述、物体识别、文字识别等",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "分析提示词，指定需要关注的重点或问题"
                            },
                            "image_url": {
                                "type": "string",
                                "description": "图片URL（HTTP/HTTPS）或base64 data URL格式"
                            }
                        },
                        "required": ["prompt", "image_url"]
                    }
                }
            }
        ]
        
        return tools
    
    @staticmethod
    def encode_image_to_base64(
        image_path: Path,
        max_size: int = 1024,
        quality: int = 85,
    ) -> Optional[str]:
        """
        将图片编码为base64字符串（带压缩和尺寸限制）
        
        基于原项目encode_image_to_base64函数的实现。
        
        Args:
            image_path: 图片文件路径
            max_size: 图片最大边长（像素），超过则等比缩放
            quality: JPEG压缩质量（1-100，越小文件越小）
            
        Returns:
            Optional[str]: base64编码的字符串，失败返回None
            
        Examples:
            >>> encoded = MiniMaxMCPClient.encode_image_to_base64(Path("photo.jpg"))
            >>> if encoded:
            ...     print(f"编码成功，长度: {len(encoded)}")
        """
        try:
            image_path = Path(image_path)
            
            if not image_path.exists():
                logger.error(f"❌ 图片文件不存在: {image_path}")
                return None
            
            file_size = image_path.stat().st_size
            if file_size == 0 or file_size < 100:
                logger.warning(f"⚠️  图片文件过小或为空: {image_path} ({file_size} bytes)")
                return None
            
            # 验证并加载图片
            img = Image.open(image_path)
            img.verify()
            img = Image.open(image_path)
            img.load()
            
            # 转换RGBA为RGB（JPEG不支持透明通道）
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            elif img.mode == 'P':
                img = img.convert('RGB')
            
            # 等比缩放（如果超过最大尺寸）
            if max(img.size) > max_size:
                ratio = max_size / float(max(img.size))
                new_size = tuple([int(x * ratio) for x in img.size])
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.debug(f"📐 图片缩放: {img.size} → {new_size}")
            
            # 编码为JPEG格式的base64
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=quality)
            encoded = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")
            
            logger.debug(
                f"🖼️  图片编码成功: {image_path.name} "
                f"({img.size[0]}x{img.size[1]}, {len(encoded)//1024}KB)"
            )
            
            return encoded
            
        except Exception as e:
            logger.error(f"❌ 图片编码失败 {image_path}: {e}")
            return None
    
    async def understand_image_via_mcp(
        self,
        image_path: Path,
        prompt: str,
    ) -> Optional[str]:
        """
        通过MCP协议调用understand_image工具理解图片
        
        基于原项目understand_image_via_mcp()的实现。
        
        使用MiniMax的MCP tool_call机制：
        1. 发送包含tool定义的请求
        2. 模型返回tool_calls
        3. 从响应中提取结果
        
        Args:
            image_path: 图片文件路径
            prompt: 分析提示词
            
        Returns:
            Optional[str]: 图片分析结果文本，失败返回None
        """
        request_id = str(uuid.uuid4())[:8]
        
        # 编码图片
        encoded = self.encode_image_to_base64(
            image_path,
            max_size=self.image_max_size,
            quality=self.image_quality,
        )
        if not encoded:
            logger.error(f"❌ [REQ-{request_id}] 图片编码失败")
            return None
        
        # 构建base64 data URL
        image_data_url = f"data:image/jpeg;base64,{encoded}"
        
        # 构建MCP请求payload
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "tools": self._mcp_tools,
            "tool_choice": {
                "type": "function",
                "function": {"name": "understand_image"},
            },
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"请使用understand_image工具分析以下图片: {image_data_url}\n\n"
                        f"提示: {prompt}"
                    ),
                }
            ],
        }
        
        logger.info(f"🔍 [REQ-{request_id}] 开始MCP图片分析: {image_path.name}")
        
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.info(f"⏳ [REQ-{request_id}] 第{attempt}次重试，等待 {delay}s...")
                    await asyncio.sleep(delay)
                
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    
                    if response.status_code != 200:
                        error_text = response.text[:300]
                        logger.error(
                            f"❌ [REQ-{request_id}] API错误 "
                            f"(HTTP {response.status_code}): {error_text}"
                        )
                        last_error = Exception(f"API错误 {response.status_code}: {error_text}")
                        continue
                    
                    data = response.json()
                    
                    # 解析MCP响应
                    if 'choices' in data and len(data['choices']) > 0:
                        message = data['choices'][0].get('message', {})
                        
                        # 情况1: 模型直接返回内容（某些情况下可能跳过tool_call）
                        if message.get('content'):
                            content = message['content'].strip()
                            logger.success(
                                f"✅ [REQ-{request_id}] MCP分析完成 "
                                f"(直接返回内容, {len(content)}字符)"
                            )
                            self._stats["success_count"] += 1
                            return content
                        
                        # 情况2: 返回tool_calls（标准MCP流程）
                        if message.get('tool_calls'):
                            logger.info(
                                f"📋 [REQ-{request_id}] 收到tool_calls响应"
                            )
                            
                            # 提取第一个tool_call的结果
                            tool_call = message['tool_calls'][0]
                            
                            # 注意：MiniMax MCP可能在tool_call中返回结果，
                            # 也可能需要再次调用来获取结果
                            # 这里我们尝试从可用字段中提取
                            if 'result' in tool_call:
                                result = tool_call['result']
                                logger.success(
                                    f"✅ [REQ-{request_id}] MCP分析完成 "
                                    f"(tool_call结果, {len(str(result))}字符)"
                                )
                                self._stats["success_count"] += 1
                                return str(result)
                            
                            # 如果没有明确的结果字段，返回content或空
                            fallback_content = message.get('content', 'MCP调用已执行但未返回明确结果')
                            logger.warning(
                                f"⚠️  [REQ-{request_id}] tool_calls无明确结果字段"
                            )
                            self._stats["success_count"] += 1
                            return fallback_content if fallback_content else None
                    
                    logger.warning(f"⚠️  [REQ-{request_id}] 响应格式异常")
                    return None
                    
            except httpx.TimeoutException:
                last_error = Exception("请求超时")
                logger.warning(f"⚠️  [REQ-{request_id}] 第{attempt}次超时")
            except Exception as e:
                last_error = e
                logger.error(f"❌ [REQ-{request_id}] 第{attempt}次异常: {e}", exc_info=True)
        
        # 所有重试失败
        self._stats["fail_count"] += 1
        logger.error(f"❌ [REQ-{request_id}] MCP调用最终失败: {last_error}")
        return None
    
    async def understand_image_direct(
        self,
        image_path: Path,
        prompt: str,
    ) -> Optional[str]:
        """
        直接调用MiniMax视觉API（不使用MCP协议）
        
        作为MCP模式的备用方案，当MCP不可用或失败时使用。
        使用标准的OpenAI兼容的多模态消息格式。
        
        Args:
            image_path: 图片文件路径
            prompt: 分析提示词
            
        Returns:
            Optional[str]: 图片分析结果文本，失败返回None
        """
        request_id = str(uuid.uuid4())[:8]
        
        # 编码图片
        encoded = self.encode_image_to_base64(
            image_path,
            max_size=self.image_max_size,
            quality=self.image_quality,
        )
        if not encoded:
            logger.error(f"❌ [REQ-{request_id}] 图片编码失败")
            return None
        
        # 构建标准多模态请求
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}",
                            },
                        },
                    ],
                }
            ],
        }
        
        logger.info(f"🖼️  [REQ-{request_id}] 开始直连图片分析: {image_path.name}")
        
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.info(f"⏳ [REQ-{request_id}] 第{attempt}次重试，等待 {delay}s...")
                    await asyncio.sleep(delay)
                
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    
                    if response.status_code != 200:
                        error_text = response.text[:300]
                        logger.error(
                            f"❌ [REQ-{request_id}] API错误 "
                            f"(HTTP {response.status_code}): {error_text}"
                        )
                        last_error = Exception(f"API错误 {response.status_code}: {error_text}")
                        continue
                    
                    data = response.json()
                    
                    if 'choices' in data and len(data['choices']) > 0:
                        content = data['choices'][0]['message']['content']
                        
                        if content and content.strip():
                            logger.success(
                                f"✅ [REQ-{request_id}] 直连分析完成 ({len(content)}字符)"
                            )
                            self._stats["success_count"] += 1
                            return content.strip()
                        else:
                            logger.warning(f"⚠️  [REQ-{request_id}] 返回内容为空")
                            return None
                    
                    return None
                    
            except httpx.TimeoutException:
                last_error = Exception("请求超时")
                logger.warning(f"⚠️  [REQ-{request_id}] 第{attempt}次超时")
            except Exception as e:
                last_error = e
                logger.error(f"❌ [REQ-{request_id}] 第{attempt}次异常: {e}", exc_info=True)
        
        self._stats["fail_count"] += 1
        logger.error(f"❌ [REQ-{request_id}] 直连调用最终失败: {last_error}")
        return None
    
    async def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        prefer_mcp: bool = True,
    ) -> Tuple[Optional[str], str]:
        """
        智能图片分析（自动选择MCP或直连模式）
        
        优先使用MCP模式，失败时自动降级为直连模式。
        
        Args:
            image_path: 图片文件路径
            prompt: 分析提示词
            prefer_mcp: 是否优先使用MCP模式（默认True）
            
        Returns:
            Tuple[Optional[str], str]: 
                - 分析结果文本（失败为None）
                - 使用的模式 ("mcp" / "direct" / "failed")
        """
        self._stats["total_calls"] += 1
        
        # 尝试MCP模式
        if prefer_mcp and self.use_mcp:
            try:
                self._stats["mcp_calls"] += 1
                result = await self.understand_image_via_mcp(image_path, prompt)
                
                if result:
                    return result, "mcp"
                
                logger.warning(f"⚠️  MCP模式失败，尝试降级为直连模式...")
                
            except Exception as e:
                logger.error(f"❌ MCP模式异常: {e}, 将使用直连模式")
        
        # 降级为直连模式
        self._stats["direct_calls"] += 1
        result = await self.understand_image_direct(image_path, prompt)
        
        if result:
            return result, "direct"
        
        return None, "failed"
    
    def get_stats(self) -> Dict[str, Any]:
        """获取调用统计信息"""
        return dict(self._stats)


class VideoAudioExtractor:
    """
    视频音频提取器
    
    使用ffmpeg从视频中提取音频轨道，
    用于后续的Whisper语音转文字处理。
    
    基于原项目minimax_mcp_multimodal_label_materials.py中的实现。
    """
    
    @staticmethod
    def extract_audio_from_video(
        video_path: Path,
        output_dir: Path = None,
        output_format: str = "wav",
    ) -> Optional[Path]:
        """
        从视频文件中提取音频
        
        使用ffmpeg将视频转换为WAV格式音频，
        参数针对Whisper模型优化（16kHz, 16bit PCM, 单声道）。
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录（默认为视频同目录）
            output_format: 输出音频格式（wav/mp3/aac）
            
        Returns:
            Optional[Path]: 提取的音频文件路径，失败返回None
            
        Examples:
            >>> audio_path = VideoAudioExtractor.extract_audio_from_video(
            ...     Path("video.mp4"),
            ...     Path("./audio_output")
            ... )
            >>> if audio_path:
            ...     print(f"音频提取成功: {audio_path}")
        """
        from .video_utils import check_ffmpeg_available
        
        video_path = Path(video_path)
        
        if not video_path.exists():
            logger.error(f"❌ 视频文件不存在: {video_path}")
            return None
        
        if not check_ffmpeg_available():
            logger.error("❌ ffmpeg未安装或不在PATH中")
            return None
        
        # 设置输出目录和文件名
        if output_dir is None:
            output_dir = video_path.parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        output_filename = f"{video_path.stem}_audio.{output_format}"
        output_path = output_dir / output_filename
        
        logger.info(f"🎬 开始提取音频: {video_path.name} → {output_filename}")
        
        try:
            # 构建ffmpeg命令（参数优化用于Whisper）
            cmd = [
                "ffmpeg",
                "-i", str(video_path),           # 输入视频
                "-vn",                            # 不包含视频流
                "-acodec", "pcm_s16le",          # 音频编解码器: PCM 16位小端序
                "-ar", "16000",                   # 采样率: 16kHz（Whisper推荐）
                "-ac", "1",                       # 声道数: 单声道
                "-y",                             # 覆盖已存在文件
                "-loglevel", "error",             # 只显示错误
                str(output_path),                 # 输出文件
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,  # 5分钟超时
            )
            
            if result.returncode == 0 and output_path.exists():
                audio_size = output_path.stat().st_size / (1024 * 1024)
                logger.success(
                    f"✅ 音频提取成功: {output_filename} ({audio_size:.1f}MB)"
                )
                return output_path
            else:
                error_msg = result.stderr.decode('utf-8', errors='ignore')[:200]
                logger.error(f"❌ 音频提取失败: {error_msg}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ 音频提取超时（>5分钟）: {video_path}")
            return None
        except FileNotFoundError:
            logger.error("❌ ffmpeg未找到，请确保已安装并在PATH中")
            return None
        except Exception as e:
            logger.error(f"❌ 音频提取异常: {e}", exc_info=True)
            return None


class WhisperTranscriber:
    """
    Whisper语音转文字器
    
    支持两种模式：
    1. OpenAI Whisper API（需要API Key）
    2. 本地Whisper模型（需要安装openai-whisper包）
    
    基于原项目transcribe_audio_whisper()的实现。
    """
    
    def __init__(
        self,
        openai_api_key: str = None,
        local_model_name: str = "base",
        language: str = "zh",
    ):
        """
        初始化Whisper转录器
        
        Args:
            openai_api_key: OpenAI API Key（用于云端Whisper）
            local_model_name: 本地模型名称（tiny/base/small/medium/large）
            language: 语言代码（zh/en/ja等）
        """
        self.openai_api_key = openai_api_key
        self.local_model_name = local_model_name
        self.language = language
        self._local_model = None
        
        logger.info(
            f"🎤 Whisper转录器初始化 | "
            f"语言: {language} | "
            f"模式: {'API' if openai_api_key else '本地'}"
        )
    
    async def transcribe(self, audio_path: Path) -> Optional[str]:
        """
        转录音频文件为文字
        
        自动选择API或本地模式。
        
        Args:
            audio_path: 音频文件路径（WAV/MP3/AAC等格式）
            
        Returns:
            Optional[str]: 转录的文字内容，失败返回None
        """
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            logger.error(f"❌ 音频文件不存在: {audio_path}")
            return None
        
        # 优先使用API模式
        if self.openai_api_key:
            result = await self._transcribe_with_api(audio_path)
            if result:
                return result
        
        # 降级为本地模式
        return await self._transcribe_with_local(audio_path)
    
    async def _transcribe_with_api(self, audio_path: Path) -> Optional[str]:
        """使用OpenAI Whisper API转录"""
        try:
            url = "https://api.openai.com/v1/audio/transcriptions"
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
            }
            
            logger.info(f"🌐 使用Whisper API转录: {audio_path.name}")
            
            async with httpx.AsyncClient(timeout=120) as client:
                with open(audio_path, 'rb') as audio_file:
                    files = {
                        'file': (audio_path.name, audio_file, 'audio/wav'),
                        'model': (None, 'whisper-1'),
                        'language': (None, self.language),
                    }
                    
                    response = await client.post(url, headers=headers, files=files)
                    
                    if response.status_code == 200:
                        data = response.json()
                        text = data.get('text', '').strip()
                        logger.success(f"✅ Whisper API转录完成 ({len(text)}字符)")
                        return text
                    else:
                        logger.error(
                            f"❌ Whisper API错误 ({response.status_code}): "
                            f"{response.text[:200]}"
                        )
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Whisper API调用异常: {e}", exc_info=True)
            return None
    
    async def _transcribe_with_local(self, audio_path: Path) -> Optional[str]:
        """使用本地Whisper模型转录"""
        try:
            import whisper
            
            logger.info(f"💻 使用本地Whisper模型转录: {audio_path.name}")
            
            # 加载模型（懒加载，只加载一次）
            if self._local_model is None:
                logger.info(f"📥 加载Whisper模型: {self.local_model_name}")
                self._local_model = whisper.load_model(self.local_model_name)
            
            # 在线程池中运行同步的whisper.transcribe
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._local_model.transcribe(
                    str(audio_path),
                    language=self.language,
                    fp16=False,  # CPU模式下禁用FP16
                ),
            )
            
            text = result.get('text', '').strip()
            logger.success(f"✅ 本地Whisper转录完成 ({len(text)}字符)")
            return text
            
        except ImportError:
            logger.warning(
                "⚠️  未安装openai-whisper包，无法使用本地Whisper。"
                "安装命令: pip install openai-whisper"
            )
            return None
        except Exception as e:
            logger.error(f"❌ 本地Whisper异常: {e}", exc_info=True)
            return None


class MultimodalMaterialProcessor:
    """
    多模态素材处理器（整合MCP + 视频 + 音频）
    
    将MCP客户端、视频直接分析、音频提取、语音转录整合为统一的工作流，
    用于处理包含图片、视频、音频的复杂素材。
    
    基于原项目minimax_mcp_multimodal_label_materials.py的完整实现。
    """
    
    def __init__(
        self,
        mcp_client: MiniMaxMCPClient,
        enable_video_processing: bool = True,
        enable_audio_transcription: bool = False,
        whisper_api_key: str = None,
    ):
        """
        初始化多模态处理器
        
        Args:
            mcp_client: MiniMax MCP客户端实例
            enable_video_processing: 是否启用视频处理（VLM直接分析）
            enable_audio_transcription: 是否启用音频转录（需要Whisper）
            whisper_api_key: OpenAI API Key（用于Whisper API，可选）
        """
        self.mcp_client = mcp_client
        self.enable_video_processing = enable_video_processing
        self.enable_audio_transcription = enable_audio_transcription
        
        # 初始化子组件
        self.audio_extractor = VideoAudioExtractor()
        self.whisper_transcriber = (
            WhisperTranscriber(openai_api_key=whisper_api_key)
            if enable_audio_transcription
            else None
        )
        
        logger.info(
            f"🎯 多模态处理器初始化 | "
            f"视频处理: {'启用' if enable_video_processing else '禁用'} | "
            f"音频转录: {'启用' if enable_audio_transcription else '禁用'}"
        )
    
    async def process_single_material(
        self,
        material_folder: Path,
        analysis_prompt: str,
    ) -> Dict[str, Any]:
        """
        处理单个素材文件夹（支持图片/视频/混合）
        
        工作流程：
        1. 扫描文件夹，识别媒体类型
        2. 对图片：直接MCP分析
        3. 对视频：直接传给VLM进行模板分析 → （可选）音频提取+转录
        4. 合并所有分析结果
        
        Args:
            material_folder: 素材文件夹路径
            analysis_prompt: 分析提示词
            
        Returns:
            Dict: 处理结果
                - material_id: 素材ID（文件夹名）
                - media_type: 媒体类型 (image/video/mixed)
                - image_results: 图片分析结果列表
                - video_results: 视频帧分析结果列表
                - audio_transcript: 音频转录文字（如果有）
                - combined_summary: 综合摘要
                - processing_mode: 使用的模式 (mcp/direct/mixed)
                - stats: 处理统计
        """
        material_folder = Path(material_folder)
        material_id = material_folder.name
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📁 开始处理素材: {material_id}")
        logger.info(f"{'='*60}\n")
        
        # 扫描文件夹内容
        images = []
        videos = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
            images.extend(material_folder.glob(ext))
        for ext in ["*.mp4", ".mov", ".avi"]:
            videos.extend(material_folder.glob(ext))
        
        if not images and not videos:
            logger.warning(f"⚠️  空文件夹: {material_id}")
            return {
                "material_id": material_id,
                "media_type": "empty",
                "error": "空文件夹",
                "timestamp": datetime.now().isoformat(),
            }
        
        # 判断媒体类型
        media_type = "mixed" if (images and videos) else ("video" if videos else "image")
        logger.info(f"📂 媒体类型: {media_type} | 图片: {len(images)}个 | 视频: {len(videos)}个")
        
        results = {
            "material_id": material_id,
            "media_type": media_type,
            "image_results": [],
            "video_results": [],
            "audio_transcript": None,
            "combined_summary": "",
            "processing_mode": "unknown",
            "stats": {
                "images_processed": 0,
                "videos_processed": 0,
                "frames_analyzed": 0,
                "errors": [],
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        all_modes = []
        
        # 处理图片
        for img_path in images[:5]:  # 最多处理5张图片
            try:
                logger.info(f"🖼️  分析图片 [{images.index(img_path)+1}/{min(len(images),5)}]: {img_path.name}")
                result, mode = await self.mcp_client.analyze_image(img_path, analysis_prompt)
                
                if result:
                    results["image_results"].append({
                        "filename": img_path.name,
                        "analysis": result,
                        "mode": mode,
                    })
                    results["stats"]["images_processed"] += 1
                    all_modes.append(mode)
                else:
                    results["stats"]["errors"].append(f"图片分析失败: {img_path.name}")
                    
            except Exception as e:
                logger.error(f"❌ 图片处理异常 {img_path.name}: {e}")
                results["stats"]["errors"].append(f"图片异常: {img_path.name} - {str(e)}")
        
        # 处理视频（如果启用）
        if videos and self.enable_video_processing:
            from .video_utils import VideoProcessor
            
            with VideoProcessor(
                default_fps=1.0,
                default_max_frames=30,
                default_target_count=10,
                keep_frames=False,
            ) as video_proc:
                
                for idx, video_path in enumerate(videos[:2]):  # 最多处理2个视频
                    try:
                        logger.info(
                            f"\n🎬 处理视频 [{idx+1}/{min(len(videos),2)}]: {video_path.name}"
                        )
                        
                        # 抽帧
                        sampled_frames, video_info = video_proc.process_video(video_path)
                        results["stats"]["videos_processed"] += 1
                        
                        logger.info(
                            f"   📹 视频信息: {video_info['duration']}s, "
                            f"{video_info['width']}x{video_info['height']}"
                        )
                        
                        # 分析每个帧
                        frame_results = []
                        for frame_idx, frame_path in enumerate(sampled_frames):
                            try:
                                logger.info(
                                    f"   🖼️  分析帧 [{frame_idx+1}/{len(sampled_frames)}]: "
                                    f"{frame_path.name}"
                                )
                                
                                frame_result, mode = await self.mcp_client.analyze_image(
                                    frame_path,
                                    f"{analysis_prompt}\n(这是视频的第{frame_idx+1}帧,"
                                    f"共{len(sampled_frames)}帧)",
                                )
                                
                                if frame_result:
                                    frame_results.append({
                                        "frame_index": frame_idx,
                                        "filename": frame_path.name,
                                        "analysis": frame_result,
                                        "mode": mode,
                                    })
                                    results["stats"]["frames_analyzed"] += 1
                                    all_modes.append(mode)
                                    
                            except Exception as e:
                                logger.error(f"   ❌ 帧分析异常 {frame_path.name}: {e}")
                                results["stats"]["errors"].append(
                                    f"帧异常: {frame_path.name} - {str(e)}"
                                )
                        
                        results["video_results"].append({
                            "filename": video_path.name,
                            "video_info": video_info,
                            "frame_analyses": frame_results,
                        })
                        
                        # 音频提取和转录（如果启用）
                        if self.enable_audio_transcription and self.whisper_transcriber:
                            try:
                                logger.info(f"   🎤 提取并转录音频...")
                                audio_path = self.audio_extractor.extract_audio_from_video(
                                    video_path,
                                    output_dir=material_folder / "_temp_audio",
                                )
                                
                                if audio_path:
                                    transcript = await self.whisper_transcriber.transcribe(audio_path)
                                    if transcript:
                                        results["audio_transcript"] = transcript
                                        logger.success(
                                            f"   ✅ 音频转录完成 ({len(transcript)}字符)"
                                        )
                                        
                                        # 清理临时音频文件
                                        audio_path.unlink(missing_ok=True)
                                        
                            except Exception as e:
                                logger.error(f"   ❌ 音频处理异常: {e}")
                                results["stats"]["errors"].append(f"音频异常: {video_path.name}")
                                
                    except Exception as e:
                        logger.error(f"❌ 视频处理异常 {video_path.name}: {e}")
                        results["stats"]["errors"].append(f"视频异常: {video_path.name} - {str(e)}")
        
        # 生成综合摘要
        results["processing_mode"] = (
            "mixed" if len(set(all_modes)) > 1 else (all_modes[0] if all_modes else "none")
        )
        
        summary_parts = []
        if results["image_results"]:
            summary_parts.append(f"图片分析: {results['stats']['images_processed']}张")
        if results["video_results"]:
            summary_parts.append(
                f"视频分析: {results['stats']['videos_processed']}个视频, "
                f"{results['stats']['frames_analyzed']}帧"
            )
        if results["audio_transcript"]:
            summary_parts.append(f"音频转录: {len(results['audio_transcript'])}字符")
        
        results["combined_summary"] = "; ".join(summary_parts) if summary_parts else "无有效结果"
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 素材处理完成: {material_id}")
        logger.info(f"   结果: {results['combined_summary']}")
        logger.info(f"   模式: {results['processing_mode']}")
        logger.info(f"   错误: {len(results['stats']['errors'])}个")
        logger.info(f"{'='*60}\n")
        
        return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MiniMax MCP客户端测试")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 测试图片分析
    test_img = subparsers.add_parser("test-image", help="测试图片分析")
    test_img.add_argument("image", help="图片文件路径")
    test_img.add_argument("--prompt", default="描述这张图片的内容", help="分析提示词")
    test_img.add_argument("--api-key", required=True, help="MiniMax API Key")
    test_img.add_argument("--no-mcp", action="store_true", help="禁用MCP模式")
    
    # 测试音频提取
    test_audio = subparsers.add_parser("extract-audio", help="测试音频提取")
    test_audio.add_argument("video", help="视频文件路径")
    
    args = parser.parse_args()
    
    if args.command == "test-image":
        import asyncio
        
        async def test():
            client = MiniMaxMCPClient(
                api_key=args.api_key,
                use_mcp=not args.no_mcp,
            )
            
            result, mode = await client.analyze_image(Path(args.image), args.prompt)
            
            if result:
                print(f"\n✅ 分析成功 (模式: {mode})")
                print(f"\n{'='*60}")
                print(result)
                print(f"{'='*60}\n")
            else:
                print("\n❌ 分析失败")
            
            print(f"\n📊 统计: {client.get_stats()}")
        
        asyncio.run(test())
        
    elif args.command == "extract-audio":
        audio_path = VideoAudioExtractor.extract_audio_from_video(Path(args.video))
        if audio_path:
            print(f"\n✅ 音频提取成功: {audio_path}")
        else:
            print("\n❌ 音频提取失败")
    
    else:
        parser.print_help()