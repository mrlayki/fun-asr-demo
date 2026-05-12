import os
import sys
import subprocess
import shutil

# 设置局部缓存目录，存放在当前目录的 temp_asr_models 文件夹下
CACHE_DIR = os.path.join(os.getcwd(), "temp_asr_models")

import platform

def start_server():
    print(f"\n>>> 即将使用 uv 隔离环境启动服务...")
    print(f"模型文件将统一缓存在当前目录: {CACHE_DIR}")
    print("⚠️ 提醒: 初次启动需要下载约 2.3GB 的模型文件，请耐心等待进度条走完...")
    print("🛑 若要停止服务，请按 Ctrl+C。\n")
    
    # 设置环境变量，强制指定魔搭社区的模型下载路径
    env = os.environ.copy()
    env["MODELSCOPE_CACHE"] = CACHE_DIR
    
    # 动态构建 uv 启动参数
    uv_args = [
        "uv", "run",
        "--python", "3.10",
        "--with", "torch",
        "--with", "torchaudio",
        "--with", "funasr", 
        "--with", "websockets", 
        "--with", "modelscope"
    ]
    
    # 智能判断系统架构，填补平台兼容性大坑
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin" and machine == "x86_64":
        print("💡 检测到 Mac Intel 平台，自动锁定 llvmlite<=0.45.0 以避免底层源码编译报错...")
        uv_args.extend(["--with", "llvmlite<=0.45.0"])
        
    uv_args.extend([
        "python", "-m", "funasr.bin.websocket_server",
        "--model_dir", "FunAudioLLM/Fun-ASR-Nano-2512",
        "--vad_dir", "fsmn-vad",
        # "--punc_dir", "ct-punc",
        "--host", "0.0.0.0",
        "--port", "10095"
    ])
    
    try:
        # 使用 uv run，它会自动创建临时虚拟环境、安装依赖并运行，不会污染全局系统环境
        subprocess.run(uv_args, env=env)
    except KeyboardInterrupt:
        print("\n✅ 检测到退出指令(Ctrl+C)，服务已正常关闭。")
    except FileNotFoundError:
        print("\n❌ 错误：未找到 'uv' 命令。请确认你已安装 uv (如: brew install uv)。")
    except Exception as e:
        print(f"\n❌ 运行发生异常: {e}")

def clean_up():
    print(f"\n>>> 准备清理部署产生的模型文件...")
    if os.path.exists(CACHE_DIR):
        try:
            shutil.rmtree(CACHE_DIR)
            print(f"✅ 成功删除缓存目录: {CACHE_DIR}")
            print(f"🎉 已为您释放了约 2.3GB 的磁盘空间！")
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
        print("  [2] 🧹 清理瘦身 (彻底删除 2.3GB 模型文件)")
        print("  [0] 🚪 退出脚本")
        print("="*40)
        
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
