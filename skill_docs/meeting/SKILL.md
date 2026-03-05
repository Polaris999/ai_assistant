---
name: meeting
description: 帮助用户查询会议室、预定会议、取消会议。当用户提到会议室、订会、预约、取消会议等时使用本技能。
# 会议仅走 HTTP：环境变量 MEETING_SKILL_URL 指向后端 URL，本技能由 GenericSkill 通过 POST 执行；未配置则会议技能不加载。
executor:
  type: http
  url: ${MEETING_SKILL_URL}
---

# 会议技能

按 [Anthropic Agent Skills](https://github.com/anthropics/skills) 规范：本技能为「会议」相关任务的说明与指南，具体执行由系统工具（book_meeting、query_meeting_rooms、cancel_meeting 等）完成。

## When to use this skill

- 用户想**查会议室**：有哪些会议室、预约规则、怎么约
- 用户想**订会/预约**：明确说了时间或相对时间（如明天下午、8 天后）
- 用户想**取消会议**：取消刚定的、取消上一笔、不订了

## Steps（工作流步骤）

- **查会议室**：一步 → 选 `query_meeting_rooms`，可选传 `query`。
- **订会**：① 识别为订会意图；② 若缺时间/主题/时长，用 `reply_only` 追问；③ 参数齐备后选 `book_meeting` 并填 `title`、`start_time`、`duration_minutes`（必填）及可选 `room`、`participants`；④ 根据执行结果回复或报错（规则由后端/执行层校验）。
- **取消**：一步 → 选 `cancel_meeting`；未填 `booking_id` 时由执行层使用本会话 `last_booking_id`。

## How to use this skill

1. **识别意图**：从用户输入判断是「查」「订」还是「取消」。
2. **查会议室**：选用 `query_meeting_rooms`，无需必填参数；可选传用户原话便于检索。
3. **订会**：选用 `book_meeting`。必须从用户输入或对话历史中解析出 **开始时间**、**主题**（可默认「未命名会议」）、**时长**（可默认 60 分钟）。若用户未说时间，先用 `reply_only` 追问再订。
4. **取消**：选用 `cancel_meeting`。若用户未说预定 id，使用本会话上一笔预定（系统槽位联想）。

## Guidelines

- 时间格式：ISO 8601，如 `2026-03-05T14:00:00`；相对时间（明天、8 天后）需推断为具体日期时间。
- 预约规则：最多提前 N 天（见系统配置）、单次会议时长上限，由执行层校验；未满足时返回规则提示。
- 多轮澄清：首轮信息不足时用 `reply_only` 追问，下一轮用户补充后再选 `book_meeting`。

## Keywords

会议室、订会、预约、取消会议、查会议室、有哪些会议室、预定、取消刚定的
