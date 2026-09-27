from __future__ import annotations
import base64, json
from typing import Any
from .config import settings
from .analysis_engine import heuristic_ai, clamp

class AIEngine:
    def __init__(self):
        self.enabled=bool(settings.openai_api_key)
        self.client=None
        if self.enabled:
            try:
                from openai import OpenAI
                self.client=OpenAI(api_key=settings.openai_api_key)
            except Exception:
                self.enabled=False

    def analyze(self, symbol:str, bundle:dict, deterministic:dict) -> dict:
        fallback=heuristic_ai(deterministic)
        if not self.enabled or not self.client:return fallback
        evidence={
            "symbol":symbol,"price":bundle.get("price"),"fundamentals":bundle.get("fundamentals"),
            "deterministic_score":deterministic.get("deterministic_score"),"score_breakdown":deterministic.get("breakdown"),
            "technicals":deterministic.get("technicals"),"levels":deterministic.get("levels"),"news":deterministic.get("news"),
            "risk_reward":deterministic.get("risk_reward"),"deterministic_expected_yield_pct":deterministic.get("expected_yield_pct"),
        }
        schema={"type":"object","additionalProperties":False,"properties":{
            "ai_score":{"type":"number"},"ai_expected_yield_pct":{"type":"number"},"holding_period_min_days":{"type":"integer"},"holding_period_max_days":{"type":"integer"},
            "reasons":{"type":"array","items":{"type":"string"}},"risks":{"type":"array","items":{"type":"string"}},
            "adjustments":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{"points":{"type":"number"},"reason":{"type":"string"}},"required":["points","reason"]}},
            "sensitivity":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{"condition":{"type":"string"},"new_score":{"type":"number"}},"required":["condition","new_score"]}}
        },"required":["ai_score","ai_expected_yield_pct","holding_period_min_days","holding_period_max_days","reasons","risks","adjustments","sensitivity"]}
        try:
            resp=self.client.responses.create(
                model=settings.openai_model,
                input=[{"role":"system","content":[{"type":"input_text","text":"You are the contextual analysis layer of a stock-research dashboard. Use only the supplied evidence. Do not invent facts. Return an auditable score rationale, not private chain-of-thought. Material negative evidence may override otherwise strong scores. Explosive-runner status must never compensate for weak fundamentals."}]},{"role":"user","content":[{"type":"input_text","text":json.dumps(evidence,default=str)}]}],
                text={"format":{"type":"json_schema","name":"stock_context_score","schema":schema,"strict":True}}
            )
            data=json.loads(resp.output_text)
            data["ai_score"]=round(clamp(float(data["ai_score"])),1); data["ai_expected_yield_pct"]=round(float(data["ai_expected_yield_pct"]),1); data["mode"]="OpenAI structured rationale"
            return data
        except Exception as exc:
            fallback["risks"].append(f"AI provider unavailable; used deterministic contextual fallback ({type(exc).__name__})")
            return fallback

    def extract_positions_from_image(self, image:bytes, mime:str="image/png") -> list[dict] | None:
        if not self.enabled or not self.client:return None
        data_url=f"data:{mime};base64,{base64.b64encode(image).decode()}"
        schema={"type":"object","additionalProperties":False,"properties":{"positions":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{"symbol":{"type":"string"},"shares":{"type":"number"},"avg_cost":{"type":"number"},"account":{"type":"string"}},"required":["symbol","shares","avg_cost","account"]}}},"required":["positions"]}
        try:
            resp=self.client.responses.create(model=settings.openai_model,input=[{"role":"user","content":[{"type":"input_text","text":"Extract only current stock positions visible in this brokerage screenshot. Use ticker symbol when visible or confidently inferable from the instrument name. Do not guess uncertain holdings. Average cost must be per-share purchase average, not current price. Return structured positions for user confirmation."},{"type":"input_image","image_url":data_url}]}],text={"format":{"type":"json_schema","name":"portfolio_positions","schema":schema,"strict":True}})
            return json.loads(resp.output_text).get("positions") or []
        except Exception:return None
