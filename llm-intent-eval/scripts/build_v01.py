#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


FAMILY_CONFIG = {
    "A": {
        "stage": "opening",
        "sidepath": None,
        "history": "您好，我是协助办理入职背调的AI语音助手，现在方便沟通吗？",
        "pending": ["确认是否方便沟通", "确认授权通知送达与办理进展"],
        "action": "HANDLE_OPENING_RESPONSE",
    },
    "B": {
        "stage": "delivery_confirmation",
        "sidepath": "a1_trust_crisis",
        "history": "之前发送的背调授权通知，您收到了吗？",
        "pending": ["解决信任问题", "返回送达确认"],
        "action": "HANDLE_TRUST_CONCERN",
    },
    "C": {
        "stage": "delivery_confirmation",
        "sidepath": "a2_reschedule",
        "history": "之前发送的背调授权通知，您收到了吗？",
        "pending": ["处理当前中断或改约", "返回授权办理主任务"],
        "action": "HANDLE_RESCHEDULE_OR_INTERRUPTION",
    },
    "D": {
        "stage": "authorization_followup",
        "sidepath": "a3_resistance",
        "history": "想确认一下您目前在授权办理上是否还有顾虑？",
        "pending": ["处理用户顾虑", "确定是否继续办理"],
        "action": "HANDLE_RESISTANCE_OR_ESCALATION",
    },
    "E": {
        "stage": "delivery_confirmation",
        "sidepath": None,
        "history": "之前通过短信或邮件发送的背调授权通知，您收到了吗？",
        "pending": ["确认通知送达情况", "推进授权完成"],
        "action": "ROUTE_DELIVERY_STATUS",
    },
    "F": {
        "stage": "uncompleted_reason",
        "sidepath": None,
        "history": "了解到您收到了但还没完成，主要是忙忘了、操作有问题，还是有其他顾虑？",
        "pending": ["确认未完成原因", "解决问题并获得完成承诺"],
        "action": "ROUTE_UNCOMPLETED_REASON",
    },
    "G": {
        "stage": "completion_troubleshooting",
        "sidepath": None,
        "history": "后台暂未显示完成，电子签名、人脸识别和最终提交都完成了吗？",
        "pending": ["定位未完成步骤", "完成授权或转人工"],
        "action": "ROUTE_COMPLETION_TROUBLESHOOTING",
    },
    "H": {
        "stage": "completion_commitment",
        "sidepath": None,
        "history": "您看今天下班前完成，可以吗？",
        "pending": ["获得明确完成时间", "收尾并记录承诺"],
        "action": "HANDLE_COMMITMENT_RESPONSE",
    },
    "I": {
        "stage": "operation_support",
        "sidepath": "a4_or_a5_support",
        "history": "您现在具体卡在哪一步，或者想确认哪项填写规则？",
        "pending": ["解决操作或填写问题", "返回授权主任务"],
        "action": "HANDLE_OPERATION_SUPPORT",
    },
}


DIRECTIVES = {
    "7-1": "按静默规则提示两次；仍无回应则结束本轮，不猜测用户意图。",
    "7-2": "按非本人或号码错误流程核实，不透露背调与委托方敏感信息。",
    "7-3": "暂停当前询问，先说明身份、来意和核验方式，再尝试回主线。",
    "7-4": "使用语音助手转接话术，仅说明必要身份和来电原因，请求转接本人。",
    "7-5": "按非本人流程只询问本人何时方便，不透露背调和委托方信息。",
    "7-6": "用户表示方便，按当前呼叫类型进入送达确认或断点续接。",
    "7-7": "暂停主流程，判断具体不方便原因并进入改约旁路。",
    "7-8": "用户直接报告已完成，跳过重复询问，先查询后台完成状态。",
    "7-9": "暂停催办，提供身份与工单核验方式，信任恢复后回原断点。",
    "7-10": "解释信息来源和授权前的信息边界，消除疑虑后回原断点。",
    "7-11": "认可防骗顾虑，提供HR或官方核验路径，未核实前不施压。",
    "7-12": "解释系统外呼号码并提供官方回拨核验方式，之后再继续。",
    "7-13": "先鉴别短信或邮件是否含授权链接，帮助区分本次通知。",
    "7-14": "先为频繁来电致歉并解释时限原因，避免继续施压。",
    "7-15": "信任已恢复，结束旁路并回到此前未完成的主线问题。",
    "7-16": "允许用户先向HR核实，记录挂起原因并安排后续跟进。",
    "7-17": "用户仍不信任并拒绝沟通，记录结果并停止当前催办。",
    "7-18": "用户正在开车，零追问立即收线，约定安全方便时再联系。",
    "7-19": "用户有紧急事务，立即停止沟通并按规则安排后续联系。",
    "7-20": "用户正在忙，可尝试一次压缩沟通；失败则询问明确回拨时间。",
    "7-21": "说明后续所需设备和步骤，询问具备条件的时间并安排跟进。",
    "7-22": "将问题归因于线路并停止当前沟通，约定信号正常时重拨。",
    "7-23": "停止电话催办，按用户要求转短信或邮件，并记录渠道偏好。",
    "7-24": "用户接受压缩沟通，只说明当前最关键的一项，不扩展话题。",
    "7-25": "复述并确认具体回拨时间，记录时间锚点后结束当前沟通。",
    "7-26": "把相对时间换算成明确时点，复述确认后记录回拨安排。",
    "7-27": "当前承诺过于模糊，温和收窄到具体时段；仍模糊则低压收线。",
    "7-28": "用户明确拒绝，停止催办并进入不再联系的终态处理。",
    "7-29": "记录在职暴露顾虑，停止施压并反馈处理，不主动联系其公司。",
    "7-30": "记录证明人提供阻力，停止施压并反馈替代处理方案。",
    "7-31": "先回应隐私范围顾虑，不继续催促；按规则解释后再确认意愿。",
    "7-32": "用户已放弃职位，停止背调催办并进入禁止再呼终态。",
    "7-33": "允许用户先向HR确认必要性，记录挂起原因并安排后续跟进。",
    "7-34": "用户投诉或情绪强烈，停止催办，记录投诉并转人工处理。",
    "7-35": "用户要求真人，停止AI继续沟通，建立人工跟进工单。",
    "7-36": "记录已收到但未完成，进入未填原因确认，避免重复询问送达。",
    "7-37": "记录用户声称已完成，跳过催办并先查询后台完成状态。",
    "7-38": "记录未收到，进入渠道排查和必要的补发流程。",
    "7-39": "给用户时间查找，先静默等待；超时后再提供搜索提示。",
    "7-40": "用户已找到通知，指导打开链接并继续完成，再获取时间承诺。",
    "7-41": "确认各处均未找到，继续下一个渠道排查或触发补发。",
    "7-42": "用户因忙忘记，避免责备，直接协商明确的完成时间。",
    "7-43": "用户操作有困难，定位具体卡点并进入操作支持旁路。",
    "7-44": "用户不愿填写或存在顾虑，暂停时间催促并先处理阻力。",
    "7-45": "指出仍缺电子签或人脸步骤，指导返回原链接完成剩余操作。",
    "7-46": "用户坚称完成，按系统同步问题记录反馈，避免要求重复操作。",
    "7-47": "提示检查最终提交状态，确认页面显示提交成功。",
    "7-48": "记录用户接受完成时限，复述承诺并进入收尾。",
    "7-49": "用户拒绝当前时限，暂停施压并进入改约协商。",
    "7-50": "记录超时限承诺，并将时间收窄到允许范围内的具体日期。",
    "7-51": "提供一次人脸识别排查指导；再次失败则记录并转人工。",
    "7-52": "先区分是否已提交及错误字段类型，再按可修改规则处理。",
    "7-53": "记录系统或链接故障，停止重复操作要求并建立技术工单。",
    "7-54": "记录具体填写口径问题，按知识或人工反馈处理后回主任务。",
    "7-55": "用户无邮箱或拒绝提供，停止索取并转人工处理。",
    "7-56": "复述确认邮箱地址，登记补发并继续获取完成承诺。",
    "7-57": "记录用户同意自主寻访，再按合规范围执行并回原流程。",
    "7-58": "记录在职暴露顾虑，停止自主联系并按在职顾虑流程处理。",
    "7-59": "记录拒绝自主寻访，降级为仅联系用户提供的证明人。",
    "CTRL-WAIT": "用户话语尚未完成，暂不推进流程，等待用户说完后再判断。",
    "CTRL-CLARIFY": "用户表达含糊，针对关键缺失信息做一次简短澄清。",
    "CTRL-UNSUPPORTED": "说明当前请求不在可处理范围，给出正确渠道后返回主任务。",
}


NEXT_ACTIONS = {
    "7-1": "WAIT_OR_END_SILENT_CALL", "7-2": "ENTER_NON_SELF_FLOW", "7-3": "ENTER_TRUST_SIDEPATH",
    "7-4": "REQUEST_TRANSFER", "7-5": "HANDLE_NON_SELF_WITH_PRIVACY", "7-6": "CONTINUE_MAIN_FLOW",
    "7-7": "ENTER_RESCHEDULE_SIDEPATH", "7-8": "CHECK_COMPLETION_STATUS", "7-9": "PROVIDE_IDENTITY_VERIFICATION",
    "7-10": "EXPLAIN_INFORMATION_SOURCE", "7-11": "PROVIDE_OFFICIAL_VERIFICATION", "7-12": "EXPLAIN_CALLER_NUMBER",
    "7-13": "DISAMBIGUATE_CHANNEL_MESSAGES", "7-14": "APOLOGIZE_FOR_REPEAT_CALLS", "7-15": "RESUME_RETURN_POINT",
    "7-16": "SCHEDULE_FOLLOWUP_AFTER_VERIFICATION", "7-17": "END_UNTRUSTED_CALL", "7-18": "END_AND_RESCHEDULE_FOR_SAFETY",
    "7-19": "END_AND_FOLLOW_UP_LATER", "7-20": "TRY_COMPRESSION_OR_RESCHEDULE", "7-21": "ARRANGE_WHEN_CONDITIONS_AVAILABLE",
    "7-22": "END_AND_REDIAL", "7-23": "SWITCH_TO_ASYNC_CHANNEL", "7-24": "DELIVER_ONE_KEY_ITEM",
    "7-25": "CONFIRM_CALLBACK_TIME", "7-26": "NORMALIZE_AND_CONFIRM_TIME", "7-27": "NARROW_TO_SPECIFIC_TIME",
    "7-28": "ENTER_DO_NOT_CONTACT_TERMINAL", "7-29": "RECORD_EMPLOYMENT_CONCERN", "7-30": "RECORD_REFERENCE_RESISTANCE",
    "7-31": "HANDLE_PRIVACY_CONCERN", "7-32": "ENTER_OFFER_DECLINED_TERMINAL", "7-33": "PAUSE_FOR_HR_CONFIRMATION",
    "7-34": "CREATE_COMPLAINT_TICKET", "7-35": "CREATE_HUMAN_HANDOFF", "7-36": "ASK_UNCOMPLETED_REASON",
    "7-37": "CHECK_COMPLETION_STATUS", "7-38": "START_CHANNEL_TROUBLESHOOTING", "7-39": "WAIT_FOR_SEARCH",
    "7-40": "GUIDE_OPEN_AND_COMPLETE", "7-41": "CONTINUE_CHANNEL_CASCADE", "7-42": "ASK_COMPLETION_TIME",
    "7-43": "ENTER_OPERATION_SUPPORT", "7-44": "ENTER_RESISTANCE_SIDEPATH", "7-45": "GUIDE_REMAINING_STEPS",
    "7-46": "REPORT_SYNC_ISSUE", "7-47": "CHECK_FINAL_SUBMISSION", "7-48": "CLOSE_WITH_COMMITMENT",
    "7-49": "ENTER_RESCHEDULE_SIDEPATH", "7-50": "NARROW_OVERDUE_COMMITMENT", "7-51": "GUIDE_FACE_RECOGNITION",
    "7-52": "ROUTE_CORRECTION_REQUEST", "7-53": "CREATE_TECHNICAL_TICKET", "7-54": "ANSWER_OR_ESCALATE_FORM_RULE",
    "7-55": "CREATE_HUMAN_HANDOFF", "7-56": "CONFIRM_EMAIL_AND_RESEND", "7-57": "RECORD_INFORMED_CONSENT",
    "7-58": "HANDLE_EMPLOYMENT_EXPOSURE_CONCERN", "7-59": "DOWNGRADE_TO_PROVIDED_ONLY",
    "CTRL-WAIT": "WAIT_FOR_UTTERANCE_COMPLETION", "CTRL-CLARIFY": "ASK_ONE_CLARIFYING_QUESTION",
    "CTRL-UNSUPPORTED": "REDIRECT_AND_RESUME",
}


STATE_UPDATES = {
    "7-8": {"completion_claimed": True}, "7-15": {"trust_recovered": True},
    "7-16": {"verification_pending": True}, "7-17": {"conversation_terminal": True},
    "7-18": {"safety_interrupt": "driving"}, "7-19": {"safety_interrupt": "emergency"},
    "7-23": {"preferred_channel": "async"}, "7-25": {"callback_time_source": "explicit"},
    "7-26": {"callback_time_source": "relative"}, "7-27": {"weak_commitment": True},
    "7-28": {"refused": True, "conversation_terminal": True},
    "7-32": {"offer_declined": True, "conversation_terminal": True},
    "7-34": {"human_needed": True}, "7-35": {"human_needed": True},
    "7-36": {"notification_received": True, "authorization_completed": False},
    "7-37": {"notification_received": True, "completion_claimed": True},
    "7-38": {"notification_received": False}, "7-40": {"notification_received": True},
    "7-41": {"notification_received": False}, "7-42": {"uncompleted_reason": "busy_or_forgot"},
    "7-43": {"uncompleted_reason": "operation_problem"}, "7-44": {"uncompleted_reason": "resistance"},
    "7-48": {"completion_commitment": "accepted"}, "7-49": {"completion_commitment": "rejected_or_hesitant"},
    "7-50": {"completion_commitment": "outside_allowed_window"}, "7-53": {"human_needed": True},
    "7-55": {"human_needed": True}, "7-57": {"autonomous_search_consent": True},
    "7-58": {"autonomous_search_consent": "concern"}, "7-59": {"autonomous_search_consent": False},
}


CRITICAL = {"7-2", "7-5", "7-17", "7-18", "7-19", "7-28", "7-32", "7-34", "7-35", "7-53", "7-55"}


CONFUSION_GROUPS = [
    ["7-2", "7-5", "7-28", "7-32"], ["7-3", "7-9", "7-10", "7-11", "7-12"],
    ["7-6", "7-7", "7-20", "7-24"], ["7-8", "7-37", "7-46", "7-47"],
    ["7-13", "7-38", "7-39", "7-40"], ["7-14", "7-17", "7-28", "7-34"],
    ["7-15", "7-16", "7-17", "7-33"], ["7-18", "7-19", "7-20", "7-22"],
    ["7-21", "7-23", "7-25", "7-27"], ["7-25", "7-26", "7-27", "7-50"],
    ["7-29", "7-30", "7-31", "7-58"], ["7-34", "7-35", "7-28", "7-17"],
    ["7-36", "7-37", "7-38", "7-39"], ["7-39", "7-40", "7-41", "7-38"],
    ["7-42", "7-43", "7-44", "7-31"], ["7-45", "7-46", "7-47", "7-53"],
    ["7-48", "7-49", "7-50", "7-27"], ["7-51", "7-52", "7-53", "7-43"],
    ["7-54", "7-31", "7-44", "7-52"], ["7-55", "7-56", "7-23", "7-35"],
    ["7-57", "7-58", "7-59", "7-29"],
]


def parse_intents(path: Path):
    intents = {}
    family = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"### 7-([A-I]) ", raw)
        if heading:
            family = heading.group(1)
            continue
        if not raw.startswith("|") or family is None:
            continue
        cols = [c.strip().replace("**", "") for c in raw.strip().strip("|").split("|")]
        if not cols or not re.fullmatch(r"7-\d+", cols[0]):
            continue
        intent_id, name, definition, example = cols[:4]
        example = example.replace("（", "").replace("）", "").strip()
        quoted = re.findall(r'"([^"]+)"', example)
        user_text = quoted[0] if quoted else example
        intents[intent_id] = {
            "id": intent_id,
            "name": name,
            "definition": definition,
            "example": user_text,
            "family": family,
        }
    return intents


def candidate_ids_for(gold, intents):
    for group in CONFUSION_GROUPS:
        if gold in group:
            return [x for x in group if x in intents]
    family = intents[gold]["family"]
    same = [x for x, item in intents.items() if item["family"] == family]
    pos = same.index(gold)
    ordered = [gold] + same[pos + 1:] + same[:pos]
    return ordered[:4]


def response_requirements(intent_id, intent):
    directive = DIRECTIVES[intent_id]
    first_clause = re.split(r"[，；。]", directive)[0]
    must_not = []
    if intent_id in {"7-2", "7-5"}:
        must_not = ["透露背调或委托方敏感信息"]
    elif intent_id in {"7-18", "7-19"}:
        must_not = ["继续追问或催办"]
    elif intent_id in {"7-17", "7-28", "7-32"}:
        must_not = ["继续施压或推进授权"]
    elif intent_id in {"7-34", "7-35", "7-53", "7-55"}:
        must_not = ["忽略人工处理要求继续自动催办"]
    else:
        must_not = ["编造产品文档未提供的事实"]
    resume = None if intent_id in CRITICAL and intent_id not in {"7-2", "7-5"} else "继续尚未完成的授权任务"
    return {"must_include": [first_clause], "must_not_include": must_not, "resume_goal": resume}


def base_state(config, intent_id):
    state = {
        "current_stage": config["stage"],
        "active_sidepath": None,
        "collected_facts": {
            "identity_verified": True,
            "notification_received": "unknown",
            "authorization_completed": "unknown",
            "completion_commitment": None,
            "human_needed": False,
        },
        "pending_items": config["pending"],
        "last_system_action": config["action"],
    }
    number = int(intent_id.split("-")[1]) if re.fullmatch(r"7-\d+", intent_id) else None
    if number in range(15, 18):
        state["active_sidepath"] = "a1_trust_crisis"
    elif number in range(24, 29):
        state["active_sidepath"] = "a2_reschedule"
    elif number in {40, 41}:
        state["active_sidepath"] = "b12_search"
    elif number in {51, 52, 53, 54}:
        state["active_sidepath"] = "a4_or_a5_support"
    elif number in {55, 56}:
        state["active_sidepath"] = "b16_email_fallback"
    elif number in {57, 58, 59}:
        state["active_sidepath"] = "a3_autonomous_search"
    return state


def make_case(case_id, group_id, user_text, gold, candidate_ids, intents, *,
              case_type="local", difficulty="easy", risk=None, tags=None,
              state=None, history=None, updates=None, missing=None, next_action=None,
              skip=None, forbidden=None, directive=None, must_include=None,
              must_not=None, resume_goal="__default__"):
    intent = intents[gold]
    config = FAMILY_CONFIG[intent["family"]]
    requirements = response_requirements(gold, intent)
    if must_include is not None:
        requirements["must_include"] = must_include
    if must_not is not None:
        requirements["must_not_include"] = must_not
    if resume_goal != "__default__":
        requirements["resume_goal"] = resume_goal
    return {
        "case_id": case_id,
        "group_id": group_id,
        "source_ref": ([f"催授权流程 v1.1 - 意图.md：{gold}", f"表7-{intent['family']}"]
                       if gold.startswith("7-") else ["控制器兜底规则 v0.1"]),
        "input": {
            "dialogue_state": state or base_state(config, gold),
            "history": history or [{"role": "assistant", "text": config["history"]}],
            "user_text": user_text,
            "candidate_sops": [
                {"id": cid, "name": intents[cid]["name"], "definition": intents[cid]["definition"]}
                for cid in candidate_ids
            ],
        },
        "expected": {
            "acceptable_sop_ids": [gold],
            "forbidden_sop_ids": forbidden or [],
            "expected_state_updates": updates if updates is not None else STATE_UPDATES.get(gold, {}),
            "facts_still_missing": missing or [],
            "expected_next_action": next_action or NEXT_ACTIONS[gold],
            "skip_actions": skip or [],
            "response_requirements": requirements,
            "reference_detail": directive or DIRECTIVES[gold],
        },
        "metadata": {
            "case_type": case_type,
            "difficulty": difficulty,
            "risk_level": risk or ("high" if gold in CRITICAL else "medium"),
            "tags": tags or [f"family_{intent['family']}", intent["name"]],
            "status": "draft",
        },
    }


def edge_cases(intents):
    cases = []
    common_state = {
        "current_stage": "delivery_confirmation", "active_sidepath": None,
        "collected_facts": {"identity_verified": True, "notification_received": "unknown", "authorization_completed": "unknown", "completion_commitment": None, "human_needed": False},
        "pending_items": ["确认通知送达", "获得完成时间承诺"], "last_system_action": "ASK_DELIVERY_STATUS",
    }
    cases.append(make_case(
        "edge_driving_received_001", "edge_driving_received", "收到了，不过我正在开车，晚点再说。", "7-18",
        ["7-18", "7-20", "7-36", "7-28"], intents, case_type="multi_intent", difficulty="hard", risk="high",
        state=common_state, updates={"notification_received": True, "safety_interrupt": "driving"}, forbidden=["7-28"],
        next_action="END_AND_RESCHEDULE_FOR_SAFETY", must_include=["立即停止沟通", "记录已收到通知", "安全方便时再联系"],
        must_not=["继续询问授权操作", "把晚点再说视为明确拒绝"], resume_goal="安全方便时继续授权任务",
        directive="用户正在开车，立即停止沟通；记录已收到通知，方便时再联系。",
        tags=["多意图", "安全优先", "保留次要事实"],
    ))
    cases.append(make_case(
        "edge_trust_during_delivery_001", "edge_trust_during_delivery", "先别说短信了，你们到底是谁，怎么会有我的号码？", "7-10",
        ["7-9", "7-10", "7-38", "7-39"], intents, case_type="global_interrupt", difficulty="hard", risk="high",
        state=common_state, next_action="ENTER_TRUST_SIDEPATH", must_include=["暂停送达询问", "解释信息来源", "处理后回原问题"],
        must_not=["忽略质疑继续询问短信", "直接要求点击链接"], resume_goal="确认授权通知是否送达",
        directive="暂停送达询问，先解释信息来源；消除疑虑后再回到原问题。",
        tags=["信任危机", "任意阶段切出", "断点恢复"],
    ))
    cases.append(make_case(
        "edge_complaint_progress_001", "edge_complaint_progress", "我早就填完了，你们还一直打，烦不烦，我要投诉。", "7-34",
        ["7-14", "7-34", "7-37", "7-46"], intents, case_type="multi_intent", difficulty="hard", risk="high",
        state=common_state, updates={"completion_claimed": True, "human_needed": True}, forbidden=["7-37"],
        next_action="CREATE_COMPLAINT_TICKET", must_include=["停止催办", "记录已完成声明", "转人工处理投诉"],
        must_not=["只查询完成状态而忽略投诉", "继续施压"], resume_goal=None,
        directive="停止催办，记录用户称已完成，并将投诉转人工处理。",
        tags=["投诉", "已完成声明", "高优先级覆盖"],
    ))
    jump_state = {
        "current_stage": "opening", "active_sidepath": None,
        "collected_facts": {"identity_verified": True, "notification_received": "unknown", "authorization_completed": "unknown", "completion_commitment": None, "human_needed": False},
        "pending_items": ["确认通知送达", "确认完成状态", "获得完成时间承诺"], "last_system_action": "ASK_AVAILABILITY",
    }
    cases.append(make_case(
        "edge_jump_commitment_001", "jump_commitment_dialogue", "我知道了，我今晚会把授权填完。", "7-48",
        ["7-8", "7-36", "7-48", "7-27"], intents, case_type="jump_ahead", difficulty="hard",
        state=jump_state, updates={"authorization_completed": False, "completion_commitment": "今晚"}, missing=["notification_received"],
        history=[{"role": "assistant", "text": "您好，我是协助办理入职背调的AI语音助手，现在方便沟通吗？"}],
        next_action="ASK_DELIVERY_STATUS", skip=["ASK_COMPLETION_TIME"], must_include=["记录今晚承诺", "补问是否收到通知"],
        must_not=["重复询问完成时间", "假设已经收到通知", "声称已经完成"], resume_goal="确认通知是否送达",
        directive="记录今晚完成的承诺，不再问时间；补问是否已收到授权通知。",
        tags=["提前回答后续阶段", "保留信息", "补问缺失信息"],
    ))
    backfill_state = {
        "current_stage": "delivery_confirmation", "active_sidepath": None,
        "collected_facts": {"identity_verified": True, "notification_received": "unknown", "authorization_completed": False, "completion_commitment": "今晚", "human_needed": False},
        "pending_items": ["确认通知送达"], "last_system_action": "ASK_DELIVERY_STATUS",
    }
    cases.append(make_case(
        "edge_backfill_then_skip_001", "jump_commitment_dialogue", "收到了。", "7-36",
        ["7-36", "7-37", "7-38", "7-39"], intents, case_type="jump_ahead", difficulty="hard",
        state=backfill_state, updates={"notification_received": True}, next_action="CLOSE_WITH_COMMITMENT",
        history=[
            {"role": "user", "text": "我知道了，我今晚会把授权填完。"},
            {"role": "assistant", "text": "好的，我记下您今晚处理。先确认一下，授权短信或邮件您收到了吗？"}
        ],
        skip=["ASK_UNCOMPLETED_REASON", "ASK_COMPLETION_TIME"], must_include=["确认已收到", "沿用今晚承诺", "直接收尾"],
        must_not=["再次询问完成时间", "重新询问未填原因"], resume_goal="按今晚承诺收尾",
        directive="已确认收到且已有今晚承诺，跳过原因和时间询问，直接确认并收尾。",
        tags=["补齐前置信息", "跳过已满足阶段", "避免重复询问"],
    ))
    cases.append(make_case(
        "edge_busy_vs_driving_001", "edge_busy_vs_driving", "我正开会呢，等散会再打。", "7-20",
        ["7-18", "7-19", "7-20", "7-27"], intents, case_type="local", difficulty="hard",
        next_action="TRY_COMPRESSION_OR_RESCHEDULE", must_include=["识别为忙碌而非驾驶", "尝试压缩或约明确时间"],
        must_not=["按驾驶安全事件立即终止且不问时间"],
        directive="用户在开会，尝试一次压缩沟通；不方便则约明确回拨时间。",
        tags=["最小语义差异", "在忙vs开车"],
    ))
    cases.append(make_case(
        "edge_weak_vs_refusal_001", "edge_weak_vs_refusal", "这两天再说吧，我尽量。", "7-27",
        ["7-25", "7-26", "7-27", "7-28"], intents, case_type="ambiguous", difficulty="hard",
        forbidden=["7-28"], must_include=["识别弱承诺", "收窄到具体时间"], must_not=["记录为明确拒绝"],
        directive="这是模糊弱承诺，温和收窄到具体时段，不能记为明确拒绝。",
        tags=["弱承诺vs拒绝", "时间收窄"],
    ))
    cases.append(make_case(
        "edge_operation_vs_failure_001", "edge_operation_vs_failure", "这个链接怎么用啊，我不知道从哪开始。", "7-43",
        ["7-43", "7-51", "7-53", "7-54"], intents, case_type="local", difficulty="hard",
        must_include=["识别为不会操作", "追问具体卡点"], must_not=["直接建立技术故障工单"],
        directive="用户是不清楚操作而非系统故障，先定位具体卡点并提供指导。",
        tags=["不会操作vs技术故障", "困难边界"],
    ))
    cases.append(make_case(
        "edge_privacy_source_001", "edge_privacy_source", "你们为什么有我的身份证信息，会不会泄露？", "7-10",
        ["7-9", "7-10", "7-31", "7-54"], intents, case_type="multi_intent", difficulty="hard", risk="high",
        must_include=["优先解释信息来源", "同时回应隐私边界"], must_not=["忽略疑虑继续催填"],
        directive="先解释个人信息来源，并回应隐私使用边界；处理后再回主任务。",
        tags=["信息来源", "隐私顾虑", "多意图主次"],
    ))
    cases.append(make_case(
        "edge_nonself_privacy_001", "edge_nonself_privacy", "我是他妈妈，他去上班了，你找他什么事？", "7-5",
        ["7-2", "7-3", "7-5", "7-6"], intents, case_type="global_interrupt", difficulty="hard", risk="high",
        must_include=["识别非本人", "只问本人方便时间"], must_not=["透露背调、委托方或授权详情"],
        directive="非本人接听，只询问本人何时方便，不透露背调和委托方信息。",
        tags=["非本人", "隐私红线"],
    ))
    cases.append(make_case(
        "edge_asr_driving_001", "edge_asr_driving", "我在开册呢晚点", "7-18",
        ["7-18", "7-20", "7-22", "7-27"], intents, case_type="asr_noise", difficulty="hard", risk="high",
        updates={"safety_interrupt": "driving_inferred_from_asr"}, must_include=["按可能驾驶安全事件处理", "立即停止沟通"],
        must_not=["继续催办"], directive="疑似表达正在开车，按安全优先立即停止沟通，稍后再联系。",
        tags=["ASR同音错误", "安全优先"],
    ))
    cases.append(make_case(
        "edge_incomplete_utterance_001", "edge_incomplete_utterance", "我那个短信就是……", "CTRL-WAIT",
        ["7-36", "7-38", "CTRL-WAIT", "CTRL-CLARIFY"], intents, case_type="ambiguous", difficulty="medium",
        next_action="WAIT_FOR_UTTERANCE_COMPLETION", must_include=["等待用户说完", "暂不推进流程"],
        must_not=["猜测为收到或没收到"], resume_goal="等待完整表达后继续判断",
        directive="用户尚未说完，暂不推进流程，等待完整表达后再判断。",
        tags=["半句话", "WAIT", "不可提前分类"],
    ))
    cases.append(make_case(
        "edge_ambiguous_completion_001", "edge_ambiguous_completion", "应该弄了吧，我也不太记得。", "CTRL-CLARIFY",
        ["7-37", "7-39", "7-46", "CTRL-CLARIFY"], intents, case_type="ambiguous", difficulty="hard",
        next_action="ASK_ONE_CLARIFYING_QUESTION", must_include=["不把含糊表达视为已完成", "询问是否看到提交成功"],
        must_not=["直接记录已完成", "要求用户重复全部流程"], resume_goal="确认真实完成状态",
        directive="不要记为已完成；简短确认是否看到提交成功页面。",
        tags=["完成状态含糊", "CLARIFY", "避免误判完成"],
    ))
    cases.append(make_case(
        "edge_unsupported_request_001", "edge_unsupported_request", "你能顺便帮我把入职日期改到下个月吗？", "CTRL-UNSUPPORTED",
        ["7-52", "7-54", "7-35", "CTRL-UNSUPPORTED"], intents, case_type="global_interrupt", difficulty="hard",
        next_action="REDIRECT_AND_RESUME", must_include=["说明无法处理入职日期", "建议联系HR", "返回授权事项"],
        must_not=["承诺修改入职日期", "错误进入授权表修改流程"], resume_goal="继续未完成的授权任务",
        directive="说明无法修改入职日期，建议联系HR；随后返回未完成的授权事项。",
        tags=["SOP外请求", "UNSUPPORTED", "回答后回主任务"],
    ))
    return cases


def validate_cases(cases, intents):
    seen = set()
    for case in cases:
        cid = case["case_id"]
        if cid in seen:
            raise ValueError(f"duplicate case_id: {cid}")
        seen.add(cid)
        candidate_ids = {x["id"] for x in case["input"]["candidate_sops"]}
        acceptable = set(case["expected"]["acceptable_sop_ids"])
        if not acceptable <= candidate_ids:
            raise ValueError(f"gold missing from candidates: {cid}")
        if not candidate_ids <= set(intents):
            raise ValueError(f"unknown candidate: {cid}")
        if len(candidate_ids) < 2:
            raise ValueError(f"too few candidates: {cid}")
        if case["metadata"]["status"] != "draft":
            raise ValueError(f"generated case must be draft: {cid}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent-doc", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    intents = parse_intents(args.intent_doc)
    product_intent_ids = {f"7-{i}" for i in range(1, 60)}
    if set(intents) != product_intent_ids:
        missing = sorted(product_intent_ids - set(intents))
        raise ValueError(f"failed to parse all 59 intents; missing={missing}")

    intents.update({
        "CTRL-WAIT": {"id": "CTRL-WAIT", "name": "等待完整话语", "definition": "用户话语明显尚未结束，当前不应做业务判断。", "example": "我那个短信就是……", "family": "A"},
        "CTRL-CLARIFY": {"id": "CTRL-CLARIFY", "name": "请求澄清", "definition": "用户表达完整但含义不足以安全判断，需要追问一个关键信息。", "example": "应该弄了吧", "family": "A"},
        "CTRL-UNSUPPORTED": {"id": "CTRL-UNSUPPORTED", "name": "超出处理范围", "definition": "用户请求不属于当前可执行 SOP，应给出正确渠道并返回主任务。", "example": "帮我改入职日期", "family": "A"},
    })

    cases = []
    for intent_id in sorted(product_intent_ids, key=lambda x: int(x.split("-")[1])):
        intent = intents[intent_id]
        cases.append(make_case(
            f"base_{intent_id.replace('-', '_')}_001",
            f"base_{intent_id.replace('-', '_')}",
            intent["example"], intent_id, candidate_ids_for(intent_id, intents), intents,
            difficulty="easy" if intent_id not in CRITICAL else "medium",
        ))
    cases.extend(edge_cases(intents))
    validate_cases(cases, intents)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = args.output_dir / "sop_catalog_v0.1.json"
    cases_path = args.output_dir / "cases_v0.1.jsonl"
    summary_path = args.output_dir / "summary_v0.1.json"

    def catalog_key(item_id):
        return (0, int(item_id.split("-")[1])) if re.fullmatch(r"7-\d+", item_id) else (1, item_id)

    catalog = {
        "version": "0.1",
        "status": "draft",
        "source": str(args.intent_doc),
        "intents": [intents[x] for x in sorted(intents, key=catalog_key)],
    }
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with cases_path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n")

    counts = {}
    for case in cases:
        key = case["metadata"]["case_type"]
        counts[key] = counts.get(key, 0) + 1
    summary = {
        "version": "0.1",
        "status": "draft",
        "case_count": len(cases),
        "base_case_count": 59,
        "edge_case_count": len(cases) - 59,
        "case_type_counts": counts,
        "intent_coverage": len({x for c in cases for x in c["expected"]["acceptable_sop_ids"]}),
        "review_required": True,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
