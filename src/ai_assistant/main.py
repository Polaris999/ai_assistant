"""命令行入口：文本/语音预定会议。"""
import argparse
import logging
import sys

from ai_assistant.api.agent_bootstrap import create_agent_or_placeholder
from ai_assistant.config import settings
from ai_assistant.config.health_checks import check_embedding, check_vector_store, check_vllm
from ai_assistant.voice.stt import speech_to_text

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="会议预定 Agent（LangChain+LangGraph+Dify+RAG）")
    parser.add_argument("--check-vllm", action="store_true", help="验证 vLLM 配置是否可达")
    parser.add_argument("--check-embedding", action="store_true", help="验证 Embedding 配置是否可达/可用")
    parser.add_argument("--check-vector-store", action="store_true", help="验证当前配置的向量库是否可达/可用")
    parser.add_argument("--text", type=str, help="直接传入文本，例如：明天下午3点开项目会")
    parser.add_argument("--voice", type=str, help="语音文件路径（如 .wav），将先转文字再预定")
    parser.add_argument("--no-whisper", action="store_true", help="语音文件时使用本地识别而非 Whisper")
    args = parser.parse_args()

    if args.check_vllm:
        ok = check_vllm()
        sys.exit(0 if ok else 1)
    if args.check_embedding:
        ok = check_embedding()
        sys.exit(0 if ok else 1)
    if args.check_vector_store:
        ok = check_vector_store()
        sys.exit(0 if ok else 1)

    if args.text:
        user_input = args.text
    elif args.voice:
        try:
            user_input = speech_to_text(args.voice, use_whisper=not args.no_whisper)
        except FileNotFoundError as e:
            logger.error("%s", e)
            sys.exit(1)
        if not user_input.strip():
            logger.error("语音识别结果为空")
            sys.exit(1)
        logger.info("语音识别结果: %s", user_input)
    else:
        print("请输入会议信息（或提供 --text / --voice），例如：明天下午3点开项目会，1小时，会议室A")
        user_input = input("> ").strip()
        if not user_input:
            sys.exit(0)

    agent = create_agent_or_placeholder()
    result = agent.invoke(user_input)
    print(result.get("reply", "未得到回复"))
    if result.get("error"):
        logger.warning("error: %s", result["error"])
    booking = result.get("booking")
    if booking is not None:
        bid = booking.get("id") if isinstance(booking, dict) else getattr(booking, "id", None)
        if bid:
            print("会议ID:", bid)


if __name__ == "__main__":
    main()
