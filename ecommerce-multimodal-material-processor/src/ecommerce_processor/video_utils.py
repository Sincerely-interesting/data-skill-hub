"""
视频处理工具模块 - ffmpeg视频抽帧和帧采样

提供视频素材的抽帧、采样等预处理功能，
支持电商多模态素材处理流水线。
"""
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from loguru import logger


def check_ffmpeg_available(ffmpeg_bin: str = "ffmpeg") -> bool:
    """
    检查ffmpeg是否可用
    
    Args:
        ffmpeg_bin: ffmpeg 可执行文件路径（默认 PATH 中的 ffmpeg）
    
    Returns:
        bool: ffmpeg是否可用
    """
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


# 视频自适应压缩档位：从高画质到低画质依次尝试，命中第一个体积达标的档位即返回。
# 只做整段重编码（scale + 码率），绝不抽帧/逐帧——与打标"视频直传不抽帧"约定一致。
_COMPRESS_TIERS = [
    (720, "1200k"),
    (540, "800k"),
    (480, "500k"),
    (360, "350k"),
    (320, "250k"),
    (240, "180k"),
]


def compress_video_to_fit(
    video_path: Path,
    max_bytes: int,
    ffmpeg_bin: str = "ffmpeg",
    work_dir: Optional[Path] = None,
) -> Path:
    """把视频整段重编码到目标字节预算内（用于 base64 内联时绕过端点请求体上限）。

    注意：**只做整段重编码（降分辨率 + 限码率），绝不抽帧/逐帧**，
    与打标主链路"视频直传、不抽帧"的约定保持一致。

    Args:
        video_path: 原始视频路径
        max_bytes: 目标最大原始字节数（调用方应已扣除 base64 ~33% 膨胀与其它 payload 余量）
        ffmpeg_bin: ffmpeg 可执行文件路径
        work_dir: 压缩产物临时目录（默认系统临时目录）

    Returns:
        Path: 达标的压缩文件路径；若原文件已达标 / ffmpeg 不可用 / 全部档位仍超限，
              则分别返回原文件或"尽力压到最小"的那一档。
    """
    video_path = Path(video_path)
    try:
        orig_size = video_path.stat().st_size
    except OSError:
        return video_path

    # 原文件已在预算内：无需压缩
    if orig_size <= max_bytes:
        return video_path

    if not check_ffmpeg_available(ffmpeg_bin):
        logger.warning(
            "视频超出请求体预算（%.1fMB > %.1fMB）但 ffmpeg 不可用，"
            "无法自适应压缩，将按原文件发送（可能触发 413）: %s",
            orig_size / 1e6, max_bytes / 1e6, video_path.name,
        )
        return video_path

    work_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="vid_compress_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    best_path = None
    best_size = None
    for height, bitrate in _COMPRESS_TIERS:
        out = work_dir / f"{video_path.stem}_{height}p.mp4"
        cmd = [
            ffmpeg_bin, "-y", "-i", str(video_path),
            "-vf", f"scale=-2:{height}",
            "-c:v", "libx264", "-b:v", bitrate, "-preset", "fast",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
            "-loglevel", "error", str(out),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=420)
        except Exception as e:  # noqa: BLE001
            logger.warning("视频压缩档位 %sp 执行异常: %s", height, e)
            continue
        if r.returncode != 0 or not out.exists():
            logger.warning(
                "视频压缩档位 %sp 失败: %s", height,
                (r.stderr.decode("utf-8", "ignore")[-200:] if r.stderr else "unknown"),
            )
            continue
        size = out.stat().st_size
        # 记录"当前最小"作为全部超限时的兜底
        if best_size is None or size < best_size:
            best_size, best_path = size, out
        if size <= max_bytes:
            logger.info(
                "视频自适应压缩达标: %s  %.1fMB → %.1fMB (%sp/%s)",
                video_path.name, orig_size / 1e6, size / 1e6, height, bitrate,
            )
            return out

    if best_path is not None:
        logger.warning(
            "视频全部压缩档位仍超预算，返回最小档兜底: %s  %.1fMB → %.1fMB",
            video_path.name, orig_size / 1e6, (best_size or 0) / 1e6,
        )
        return best_path

    return video_path


def compress_image_to_bytes(
    image_path: Path,
    max_side: int = 1024,
    quality: int = 80,
) -> bytes:
    """把图片降分辨率并重压为 JPEG 字节（用于打标 base64 前瘦身，缓解 413）。

    读取失败或 Pillow 不可用时回退为原始文件字节，保证不中断主流程。

    Args:
        image_path: 图片路径
        max_side: 长边最大像素（等比缩放）
        quality: JPEG 质量（1-95）

    Returns:
        bytes: 压缩后的 JPEG 字节（失败则原始字节）
    """
    image_path = Path(image_path)
    try:
        import io
        from PIL import Image

        with Image.open(image_path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        logger.warning("图片压缩失败，回退原始字节 %s: %s", image_path, e)
        try:
            return image_path.read_bytes()
        except OSError:
            return None


def extract_video_frames(
    video_path: Path,
    output_dir: Path = None,
    fps: float = 1.0,
    max_frames: int = 45,
    image_format: str = "jpg",
    image_quality: int = 2,
) -> List[Path]:
    """
    使用ffmpeg从视频中抽取关键帧
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录（默认为视频同目录下的frames子目录）
        fps: 抽帧频率（默认1fps，即每秒抽取1帧）
        max_frames: 最大帧数限制（防止过长视频产生过多帧）
        image_format: 输出图片格式（jpg/png/webp）
        image_quality: 图片质量（1-31，越小质量越高，仅对jpg有效）
        
    Returns:
        List[Path]: 抽取的帧图片路径列表（按时间排序）
        
    Raises:
        FileNotFoundError: 视频文件不存在
        RuntimeError: ffmpeg未安装或执行失败
        ValueError: 参数无效
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    
    if not video_path.suffix.lower() in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        raise ValueError(f"不支持的视频格式: {video_path.suffix}")
    
    if fps <= 0:
        raise ValueError(f"fps必须大于0，当前值: {fps}")
    
    if max_frames <= 0:
        raise ValueError(f"max_frames必须大于0，当前值: {max_frames}")
    
    if not check_ffmpeg_available():
        raise RuntimeError("ffmpeg未安装或不在PATH中，无法进行视频抽帧")
    
    # 设置输出目录
    if output_dir is None:
        output_dir = video_path.parent / f"{video_path.stem}_frames"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建输出文件名模板
    output_pattern = output_dir / f"frame_%04d.{image_format}"
    
    logger.info(f" 开始抽帧: {video_path.name}")
    logger.info(f"   FPS: {fps}, 最大帧数: {max_frames}, 格式: {image_format}")
    
    try:
        # 构建ffmpeg命令
        cmd = [
            "ffmpeg",
            "-i", str(video_path),           # 输入文件
            "-vf", f"fps={fps}",             # 视频滤镜：设置帧率
            "-q:v", str(image_quality),      # 图片质量（仅对jpg有效）
            "-vframes", str(max_frames),     # 限制最大帧数
            "-y",                            # 覆盖已存在文件
            "-loglevel", "error",            # 只显示错误信息
            str(output_pattern)              # 输出文件模板
        ]
        
        # 执行ffmpeg命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "未知错误"
            raise RuntimeError(f"ffmpeg执行失败: {error_msg}")
        
        # 收集生成的帧文件
        frames = sorted(output_dir.glob(f"frame_*.{image_format}"))
        
        logger.success(f" 抽帧完成: {len(frames)} 帧 → {output_dir}/")
        
        return frames
        
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"视频抽帧超时（>{300}秒）: {video_path}")
    except Exception as e:
        logger.error(f" 抽帧失败: {e}")
        raise


def pick_evenly(
    frames: List[Path],
    target_count: int = 10,
) -> List[Path]:
    """
    从帧序列中等间隔采样
    
    当帧数超过目标数量时，均匀选取代表性帧；
    当帧数不足时，返回全部帧。
    
    Args:
        frames: 所有帧路径列表（应按时间排序）
        target_count: 目标采样数
        
    Returns:
        List[Path]: 采样后的帧路径列表
        
    Examples:
        >>> frames = [Path(f"frame_{i:04d}.jpg") for i in range(100)]
        >>> sampled = pick_evenly(frames, target_count=10)
        >>> len(sampled)
        10
        >>> # 返回第0, 11, 22, 33, 44, 55, 66, 77, 88, 99帧
    """
    if not frames:
        return []
    
    total = len(frames)
    
    if total <= target_count:
        return list(frames)
    
    # 计算采样间隔
    step = total / target_count
    
    # 等间隔采样
    sampled_indices = [int(i * step) for i in range(target_count)]
    
    # 确保最后一帧被包含（防止浮点误差导致遗漏）
    if sampled_indices[-1] != total - 1:
        sampled_indices[-1] = total - 1
    
    sampled_frames = [frames[i] for i in sampled_indices]
    
    logger.debug(f" 帧采样: {total}帧 → {len(sampled_frames)}帧 (间隔={step:.1f})")
    
    return sampled_frames


def get_video_info(video_path: Path) -> dict:
    """
    获取视频基本信息（使用ffprobe）
    
    Args:
        video_path: 视频文件路径
        
    Returns:
        dict: 视频信息字典
            - duration: 时长（秒）
            - width: 宽度（像素）
            - height: 高度（像素）
            - fps: 帧率
            - codec: 编码格式
            - size_mb: 文件大小（MB）
            
    Raises:
        FileNotFoundError: 视频文件不存在
        RuntimeError: ffprobe执行失败
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    
    try:
        # 使用ffprobe获取视频信息
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe执行失败: {result.stderr}")
        
        import json
        info = json.loads(result.stdout)
        
        # 提取视频流信息
        video_stream = None
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
        
        if not video_stream:
            raise RuntimeError("未找到视频流信息")
        
        format_info = info.get("format", {})
        
        # 解析时长
        duration_str = format_info.get("duration", "0")
        duration = float(duration_str) if duration_str else 0
        
        # 解析帧率
        fps_str = video_stream.get("r_frame_rate", "0/1")
        if "/" in fps_str:
            num, den = map(int, fps_str.split("/"))
            fps = num / den if den != 0 else 0
        else:
            fps = float(fps_str)
        
        # 文件大小（MB）
        size_bytes = int(format_info.get("size", 0))
        size_mb = size_bytes / (1024 * 1024)
        
        video_info = {
            "duration": round(duration, 2),
            "width": video_stream.get("width", 0),
            "height": video_stream.get("height", 0),
            "fps": round(fps, 2),
            "codec": video_stream.get("codec_name", "unknown"),
            "size_mb": round(size_mb, 2),
            "path": str(video_path),
        }
        
        logger.debug(f" 视频信息: {video_path.name} - {duration:.1f}s, {video_info['width']}x{video_info['height']}, {fps:.1f}fps")
        
        return video_info
        
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"获取视频信息超时: {video_path}")
    except json.JSONDecodeError:
        raise RuntimeError(f"解析视频信息失败: {video_path}")


def cleanup_temp_frames(output_dir: Path) -> None:
    """
    清理临时抽帧文件
    
    Args:
        output_dir: 抽帧输出目录
    """
    output_dir = Path(output_dir)
    
    if not output_dir.exists():
        return
    
    try:
        shutil.rmtree(output_dir)
        logger.debug(f" 已清理临时帧目录: {output_dir}")
    except Exception as e:
        logger.warning(f" 清理临时帧目录失败: {e}")


class VideoProcessor:
    """
    视频处理器类 - 封装完整的视频处理流程
    
    提供高级接口，自动管理临时文件和错误处理。
    """
    
    def __init__(
        self,
        default_fps: float = 1.0,
        default_max_frames: int = 45,
        default_target_count: int = 10,
        keep_frames: bool = False,
    ):
        """
        初始化视频处理器
        
        Args:
            default_fps: 默认抽帧频率
            default_max_frames: 默认最大帧数
            default_target_count: 默认目标采样数
            keep_frames: 是否保留抽帧后的临时文件
        """
        self.default_fps = default_fps
        self.default_max_frames = default_max_frames
        self.default_target_count = default_target_count
        self.keep_frames = keep_frames
        self._temp_dirs: List[Path] = []
    
    def process_video(
        self,
        video_path: Path,
        fps: float = None,
        max_frames: int = None,
        target_count: int = None,
    ) -> Tuple[List[Path], dict]:
        """
        处理单个视频：抽帧 + 采样
        
        Args:
            video_path: 视频文件路径
            fps: 抽帧频率（默认使用实例默认值）
            max_frames: 最大帧数（默认使用实例默认值）
            target_count: 目标采样数（默认使用实例默认值）
            
        Returns:
            Tuple[List[Path], dict]: 
                - 采样后的帧路径列表
                - 视频信息字典
        """
        fps = fps or self.default_fps
        max_frames = max_frames or self.default_max_frames
        target_count = target_count or self.default_target_count
        
        # 获取视频信息
        video_info = get_video_info(video_path)
        
        # 创建临时输出目录
        temp_dir = tempfile.mkdtemp(prefix="video_frames_")
        temp_path = Path(temp_dir)
        self._temp_dirs.append(temp_path)
        
        try:
            # 抽帧
            all_frames = extract_video_frames(
                video_path=video_path,
                output_dir=temp_path,
                fps=fps,
                max_frames=max_frames,
            )
            
            # 采样
            sampled_frames = pick_evenly(all_frames, target_count=target_count)
            
            logger.info(
                f" 视频处理完成: {video_path.name} "
                f"({video_info['duration']}s) → {len(sampled_frames)}帧"
            )
            
            return sampled_frames, video_info
            
        except Exception as e:
            if not self.keep_frames:
                cleanup_temp_frames(temp_path)
            raise
    
    def process_videos(
        self,
        video_paths: List[Path],
        **kwargs,
    ) -> List[Tuple[List[Path], dict]]:
        """
        批量处理多个视频
        
        Args:
            video_paths: 视频文件路径列表
            **kwargs: 传递给process_video的参数
            
        Returns:
            List[Tuple]: 每个视频的处理结果列表
        """
        results = []
        
        for video_path in video_paths:
            try:
                result = self.process_video(video_path, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f" 视频处理失败 {video_path}: {e}")
                results.append(([], {"error": str(e)}))
        
        return results
    
    def cleanup(self):
        """清理所有临时文件"""
        if not self.keep_frames:
            for temp_dir in self._temp_dirs:
                cleanup_temp_frames(temp_dir)
            self._temp_dirs.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="视频处理工具")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--fps", type=float, default=1.0, help="抽帧频率")
    parser.add_argument("--max-frames", type=int, default=45, help="最大帧数")
    parser.add_argument("--target-count", type=int, default=10, help="目标采样数")
    parser.add_argument("--info", action="store_true", help="仅显示视频信息")
    parser.add_argument("--keep-frames", action="store_true", help="保留抽帧文件")
    
    args = parser.parse_args()
    
    video_path = Path(args.video)
    
    if args.info:
        info = get_video_info(video_path)
        print("\n 视频信息:")
        print(f"   文件: {info['path']}")
        print(f"   时长: {info['duration']}秒")
        print(f"   分辨率: {info['width']}x{info['height']}")
        print(f"   帧率: {info['fps']}fps")
        print(f"   编码: {info['codec']}")
        print(f"   大小: {info['size_mb']}MB\n")
    else:
        with VideoProcessor(keep_frames=args.keep_frames) as processor:
            frames, info = processor.process_video(
                video_path=video_path,
                fps=args.fps,
                max_frames=args.max_frames,
                target_count=args.target_count,
            )
            
            print(f"\n 处理完成:")
            print(f"   视频: {video_path.name}")
            print(f"   采样帧数: {len(frames)}")
            print(f"   帧文件:")
            for frame in frames:
                print(f"      - {frame.name}\n")