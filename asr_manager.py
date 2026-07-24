import os
import subprocess
import shutil

import platform


def _cache_dir() -> str:
    """魔搭缓存根目录：优先读环境变量（Docker / 运维注入），否则为当前工作目录下 temp_asr_models。"""
    return os.path.abspath(
        os.environ.get("MODELSCOPE_CACHE", os.path.join(os.getcwd(), "temp_asr_models"))
    )


def _default_asr_model() -> str:
    return os.environ.get("ASR_MODEL", "iic/SenseVoiceSmall")


def _default_asr_revision() -> str:
    return os.environ.get("ASR_MODEL_REVISION", "master")


def _need_funasr_nano_extras() -> bool:
    """Fun-ASR-Nano 等需 transformers 等依赖；宿主机 SenseVoice 默认不装以减轻体积。"""
    if os.environ.get("ASR_UV_EXTRA_DEPS", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    mid = _default_asr_model()
    return "Fun-ASR" in mid or "FunAudioLLM/Fun-ASR" in mid


def _uv_python() -> str:
    """uv 使用的 Python 版本；新版 funasr 要求 >=3.11。"""
    return os.environ.get("ASR_UV_PYTHON", "3.11").strip() or "3.11"


def start_server():
    cache_dir = _cache_dir()
    asr_model = _default_asr_model()
    asr_revision = _default_asr_revision()

    print(f"\n>>> 即将使用 uv 隔离环境启动服务...")
    print(f"模型文件将统一缓存在: {cache_dir}")
    print(f"离线 ASR 模型: {asr_model} (revision={asr_revision})")
    if "SenseVoice" in asr_model:
        print("⚠️ 提醒: 初次启动 SenseVoice 等约需下载数 GB 模型，请耐心等待进度条走完...")
    elif "Fun-ASR" in asr_model or "FunAudioLLM" in asr_model:
        print("⚠️ 提醒: Fun-ASR-Nano 权重与依赖较大，初次拉取请预留磁盘与网络...")
    else:
        print("⚠️ 提醒: 初次启动可能需要下载模型，请耐心等待...")
    print("🛑 若要停止服务，请按 Ctrl+C。\n")

    # 子进程与 ModelScope 共用同一缓存根目录（与宿主机 volume 映射路径一致即可命中已有文件）
    env = os.environ.copy()
    env["MODELSCOPE_CACHE"] = cache_dir

    uv_py = _uv_python()
    # 动态构建 uv 启动参数
    uv_args = [
        "uv",
        "run",
        "--python",
        uv_py,
    ]
    if os.environ.get("ASR_DEVICE", "").strip().lower() == "cpu":
        uv_args.extend(
            [
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
                "--extra-index-url",
                "https://pypi.org/simple",
            ]
        )
    uv_args.extend(
        [
            "--with",
            "numpy<2",
            "--with",
            "torch",
            "--with",
            "torchaudio",
            "--with",
            "funasr",
            "--with",
            "websockets",
            "--with",
            "modelscope",
        ]
    )
    if _need_funasr_nano_extras():
        # Fun-ASR-Nano / 文档与模型仓常见依赖（推理 + 日文 g2p 等）；SenseVoice 默认不装
        uv_args.extend(
            [
                "--with",
                "transformers",
                "--with",
                "tokenizers",
                "--with",
                "zhconv",
                "--with",
                "whisper_normalizer",
                "--with",
                "pyopenjtalk-plus",
                "--with",
                "compute-wer",
                "--with",
                "huggingface_hub",
                "--with",
                "scipy",
                "--with",
                "soundfile",
                "--with",
                "tiktoken",
                "--with",
                "openai-whisper",
            ]
        )
    
    # 确保官方 WebSocket 服务端脚本存在
    server_script = "funasr_wss_server.py"
    if not os.path.exists(server_script):
        print(f"📥 正在下载官方 WebSocket 服务端脚本 ({server_script})...")
        import urllib.request
        url = "https://raw.githubusercontent.com/modelscope/FunASR/main/runtime/python/websocket/funasr_wss_server.py"
        try:
            urllib.request.urlretrieve(url, server_script)
        except Exception as e:
            print(f"❌ 下载脚本失败: {e}")
            return
    
    # 智能判断系统架构，填补平台兼容性大坑
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin" and machine == "x86_64":
        print("💡 检测到 Mac Intel 自动锁定 llvmlite<=0.45.0 以避免底层源码编译报错...")
        uv_args.extend(["--with", "llvmlite<=0.45.0"])
        
    server_cmd = [
        "python",
        server_script,
        "--asr_model",
        asr_model,
        "--asr_model_revision",
        asr_revision,
        "--vad_model",
        os.environ.get("ASR_VAD_MODEL", "fsmn-vad"),
        "--host",
        os.environ.get("ASR_HOST", "0.0.0.0"),
        "--port",
        os.environ.get("ASR_PORT", "10095"),
        "--certfile",
        os.environ.get("ASR_CERTFILE", ""),
        "--keyfile",
        os.environ.get("ASR_KEYFILE", ""),
    ]
    if os.environ.get("ASR_PUNC_MODEL"):
        server_cmd.extend(["--punc_model", os.environ["ASR_PUNC_MODEL"]])
    if "ASR_DEVICE" in os.environ:
        server_cmd.extend(["--device", os.environ["ASR_DEVICE"]])
    if "ASR_NGPU" in os.environ:
        server_cmd.extend(["--ngpu", os.environ["ASR_NGPU"]])
    if "ASR_NCPU" in os.environ:
        server_cmd.extend(["--ncpu", os.environ["ASR_NCPU"]])
    if "ASR_MODEL_ONLINE" in os.environ:
        server_cmd.extend(["--asr_model_online", os.environ["ASR_MODEL_ONLINE"]])
    if "ASR_MODEL_ONLINE_REVISION" in os.environ:
        server_cmd.extend(["--asr_model_online_revision", os.environ["ASR_MODEL_ONLINE_REVISION"]])
    if "ASR_VAD_MODEL_REVISION" in os.environ:
        server_cmd.extend(["--vad_model_revision", os.environ["ASR_VAD_MODEL_REVISION"]])
    if "ASR_MAX_SEGMENT_MS" in os.environ:
        # 超长语音兜底强制切分阈值(ms)：大段无停顿音频最多累计这么久就送一次离线识别，0 关闭
        server_cmd.extend(["--max_segment_ms", os.environ["ASR_MAX_SEGMENT_MS"]])

    uv_args.extend(server_cmd)
    
    try:
        # 使用 uv run，它会自动创建临时虚拟环境、安装依赖并运行，不会污染全局系统环境
        completed = subprocess.run(uv_args, env=env)
        if completed.returncode:
            raise SystemExit(completed.returncode)
    except KeyboardInterrupt:
        print("\n✅ 检测到退出指令(Ctrl+C)，服务已正常关闭。")
    except FileNotFoundError:
        print("\n❌ 错误：未找到 'uv' 命令。请确认你已安装 uv (如: brew install uv)。")
    except Exception as e:
        print(f"\n❌ 运行发生异常: {e}")

def clean_up():
    print(f"\n>>> 准备清理部署产生的模型文件...")
    cache_dir = _cache_dir()
    if os.path.exists(cache_dir):
        try:
            shutil.rmtree(cache_dir)
            print(f"✅ 成功删除缓存目录: {cache_dir}")
            print(f"🎉 已为您释放了模型缓存占用的磁盘空间！")
        except Exception as e:
            print(f"❌ 删除目录失败，请检查文件是否被占用: {e}")
    else:
        print("ℹ️ 缓存目录不存在，你的电脑很干净，无需清理。")

def main():
    while True:
        print("\n" + "="*40)
        print(" 🎙️  FunASR 极简跨平台管理脚本 (uv 加持版)")
        print("="*40)
        print("  [1] 🚀 自动准备环境并启动服务 (使用 uv)")
        print("  [2] 🧹 清理瘦身 (删除 MODELSCOPE_CACHE 下已缓存的模型文件)")
        print("  [0] 🚪 退出脚本")
        print("="*40)
        if os.environ.get("ASR_AUTO_START") == "true":
            print("🚀 检测到 ASR_AUTO_START 环境变量，自动进入 [1] 启动服务模式...")
            start_server()
            return

        choice = input("👉 请输入序号按回车：").strip()
        
        if choice == '1':
            start_server()
        elif choice == '2':
            clean_up()
        elif choice == '0':
            print("👋 再见！")
            break
        else:
            print("⚠️ 无效的序号，请重新输入。")

if __name__ == "__main__":
    main()
