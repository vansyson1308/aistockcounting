"""Optional LLM planner on Amazon Bedrock (Converse API tool use).

The planner is offered one tool per currently *allowed* action (see
``policy.allowed_actions``). It sees only the numeric observation, never the
image, and must pick one tool (``toolChoice: {"any": {}}``). The controller
still validates the choice, applies the same step/time budget, and on any
error, timeout or invalid output switches to the deterministic policy for the
rest of the run. The approval gate is enforced in code, not by the model.

API shapes (verified against the botocore ``bedrock-runtime`` service model):
``converse(modelId, messages, system, inferenceConfig, toolConfig)`` →
``output.message.content[*].toolUse{toolUseId,name,input}``, ``stopReason``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.controller import DeterministicPlanner, Planner
from app.agent.policy import Action, Observation, PolicyConfig

logger = logging.getLogger("app")

SYSTEM_PROMPT = """You are the planning module of TrayAgent, a jewelry tray counting agent.
You receive numeric observations produced by OpenCV tools and choose the next action by
calling exactly one of the provided tools. Rules:
- Only the provided tools are allowed right now; each tool is one action.
- Prefer the cheapest action that resolves the largest uncertainty.
- Never accept a count that disagrees with the POS figure; escalate to a human instead.
- Request a re-shot only for fixable capture problems (glare, blur, tray not in frame, darkness).
- The budget is {max_steps} perception steps; {steps_left} remain.
Give a one-sentence reason in the tool input."""

DESCRIPTIONS = {
    Action.ASSESS: "Measure blur, glare, exposure and tray coverage of the photo.",
    Action.REDUCE_GLARE: "Inpaint specular highlights (OpenCV inpaint + CLAHE) before counting.",
    Action.COUNT: "Rectify the tray (homography) and run the DNN detector once.",
    Action.TILE: "Re-detect on overlapping tiles; helps dense trays of small items.",
    Action.ZOOM: "Crop and upscale the uncertain regions and re-detect them.",
    Action.COMPARE: "Align yesterday's approved photo (ORB + homography) and diff to localise changes.",
    Action.AUTO_ACCEPT: "Accept the count without a human (only offered when it is confident and matches POS).",
    Action.REQUEST_RECAPTURE: "Ask the staff member to retake the photo with a specific instruction.",
    Action.ESCALATE: "Stop and send annotated evidence to a human for approval.",
}


def tool_config(allowed: list[Action]) -> dict[str, Any]:
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": a.value,
                    "description": DESCRIPTIONS[a],
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"reason": {"type": "string"}},
                            "required": ["reason"],
                        }
                    },
                }
            }
            for a in allowed
        ],
        "toolChoice": {"any": {}},
    }


def parse_tool_choice(response: dict[str, Any]) -> tuple[Action, str]:
    content = response["output"]["message"]["content"]
    for block in content:
        use = block.get("toolUse")
        if use:
            action = Action(use["name"])
            reason = str((use.get("input") or {}).get("reason", ""))[:300]
            return action, reason
    raise ValueError(
        f"no toolUse in response (stopReason={response.get('stopReason')})"
    )


class BedrockPlanner:
    name = "bedrock"

    def __init__(self, client: Any, model_id: str, max_tokens: int = 200) -> None:
        self.client = client
        self.model_id = model_id
        self.max_tokens = max_tokens

    def propose(
        self, obs: Observation, allowed: list[Action], cfg: PolicyConfig
    ) -> tuple[Action, str]:
        if len(allowed) == 1:  # nothing to plan (e.g. the first step is always assess)
            return allowed[0], "only allowed action"
        system = SYSTEM_PROMPT.format(
            max_steps=cfg.max_steps, steps_left=max(0, cfg.max_steps - obs.steps_used)
        )
        user = "Observation:\n" + json.dumps(obs.as_dict(), sort_keys=True)
        response = self.client.converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0.0},
            toolConfig=tool_config(allowed),
        )
        return parse_tool_choice(response)


def build_planner(settings: Any) -> Planner:
    """Return the configured planner. Misconfiguration falls back to deterministic."""
    if settings.agent_planner != "bedrock":
        return DeterministicPlanner()
    if not settings.bedrock_model_id:
        logger.warning(
            "AGENT_PLANNER=bedrock but BEDROCK_MODEL_ID is empty; using deterministic"
        )
        return DeterministicPlanner()
    try:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(
                read_timeout=settings.bedrock_timeout_s,
                connect_timeout=2,
                retries={"max_attempts": 1},
            ),
        )
    except Exception:
        logger.exception("could not create the Bedrock client; using deterministic")
        return DeterministicPlanner()
    return BedrockPlanner(client, settings.bedrock_model_id)
