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
    parser = argparse.ArgumentParser(description="会议预定 Agent（Tool Use / Plan-and-Execute + 技能层 + RAG）")
    parser.add_argument("--check-vllm", action="store_true", help="验证 vLLM 配置是否可达")
    parser.add_argument("--check-embedding", action="store_true", help="验证 Embedding 配置是否可达/可用")
    parser.add_argument("--check-vector-store", action="store_true", help="验证当前配置的向量库是否可达/可用")
    parser.add_argument("--text", type=str, help="直接传入文本，例如：明天下午3点开项目会")
    parser.add_argument("--voice", type=str, help="语音文件路径（如 .wav），将先转文字再预定")
    parser.add_argument("--no-whisper", action="store_true", help="语音文件时使用本地识别而非 Whisper")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    p_create = subparsers.add_parser("create-skill", help="创建新技能脚手架（skill_docs/<id>/SKILL.md），对齐 Anthropic/LangChain skill-creator")
    p_create.add_argument("skill_id", help="技能 ID，即目录名（小写字母、数字、连字符、下划线）")
    p_create.add_argument("--name", default="", help="显示名称，默认用 skill_id")
    p_create.add_argument("--description", default="", help="简短描述")
    p_create.add_argument("--http-url", default="", help="无代码技能：填写后将在 frontmatter 写入 executor.url")
    p_create.add_argument("--overwrite", action="store_true", help="覆盖已存在的 SKILL.md")
    args = parser.parse_args()

    if getattr(args, "command", None) == "create-skill":
        try:
            from ai_assistant.config.skill_creator import create_skill
            path = create_skill(
                args.skill_id,
                name=args.name or None,
                description=args.description or None,
                http_url=args.http_url or None,
                overwrite=args.overwrite,
            )
            print(f"已创建: {path}")
        except ValueError as e:
            logger.error("%s", e)
            sys.exit(1)
        sys.exit(0)

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
