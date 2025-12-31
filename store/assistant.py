import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from django.db.models import QuerySet
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from .models import Product


DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_CHAT_COMPLETIONS_URL = f"{DASHSCOPE_BASE_URL}/chat/completions"
QWEN_MODEL = "qwen-plus"


class AssistantChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)
    budget_min = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    budget_max = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20, default=8)

    history = serializers.ListField(
        required=False,
        allow_empty=True,
        max_length=6,
        child=serializers.DictField(),
    )

    def validate_history(self, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in value:
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"}:
                raise serializers.ValidationError("history.role must be 'user' or 'assistant'")
            if not isinstance(content, str) or not content.strip():
                raise serializers.ValidationError("history.content must be a non-empty string")
            if len(content) > 1000:
                raise serializers.ValidationError("history.content too long")
            normalized.append({"role": role, "content": content.strip()})
        return normalized

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        budget_min = attrs.get("budget_min")
        budget_max = attrs.get("budget_max")
        if budget_min is not None and budget_max is not None and budget_min > budget_max:
            raise serializers.ValidationError("budget_min cannot be greater than budget_max")
        return attrs


class AssistantChatResponseSerializer(serializers.Serializer):
    class RecommendationSerializer(serializers.Serializer):
        product_id = serializers.IntegerField()
        name = serializers.CharField()
        model = serializers.CharField()
        price = serializers.CharField()
        stock = serializers.IntegerField()
        highlights = serializers.ListField(child=serializers.CharField(), required=False)
        tradeoffs = serializers.ListField(child=serializers.CharField(), required=False)
        why_fit = serializers.CharField(required=False, allow_blank=True)

    answer = serializers.CharField()
    recommendations = RecommendationSerializer(many=True)
    used_filters = serializers.DictField()


class AssistantChatThrottle(SimpleRateThrottle):
    """Rate limit assistant chat to control cost.

    - Authenticated users are keyed by user id.
    - Anonymous users are keyed by IP.

    Rate string is configured by REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['assistant_chat'].
    """

    scope = "assistant_chat"

    def get_cache_key(self, request, view):
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = f"ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


@dataclass(frozen=True)
class CandidateProduct:
    id: int
    name: str
    model: str
    price: Decimal
    stock: int
    description: str


def _get_candidate_products(
    *,
    budget_min: Optional[Decimal],
    budget_max: Optional[Decimal],
    limit: int,
) -> List[CandidateProduct]:
    qs: QuerySet[Product] = Product.objects.all()

    if budget_min is not None:
        qs = qs.filter(price__gte=budget_min)
    if budget_max is not None:
        qs = qs.filter(price__lte=budget_max)

    # Prefer in-stock items first; then closest to budget (if provided), else cheaper first.
    qs = qs.order_by("-stock", "price")

    products: List[CandidateProduct] = []
    for p in qs[: max(limit, 1)]:
        products.append(
            CandidateProduct(
                id=p.id,
                name=p.name,
                model=p.model,
                price=p.price,
                stock=p.stock,
                description=p.description,
            )
        )
    return products


def _build_catalog_block(candidates: Sequence[CandidateProduct]) -> str:
    if not candidates:
        return "CATALOG is empty."

    lines = ["CATALOG (from database; do not invent fields)"]
    for p in candidates:
        # Keep it compact to control tokens.
        desc = (p.description or "").replace("\n", " ").strip()
        if len(desc) > 400:
            desc = desc[:400] + "..."
        lines.append(
            f"- id: {p.id}; name: {p.name}; model: {p.model}; price: {p.price}; stock: {p.stock}; description: {desc}"
        )
    return "\n".join(lines)


def _response_json_schema() -> Dict[str, Any]:
    # Schema focuses the model on selecting product_id and providing reasons.
    return {
        "name": "assistant_chat_response",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "string"},
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "product_id": {"type": "integer"},
                            "highlights": {"type": "array", "items": {"type": "string"}},
                            "tradeoffs": {"type": "array", "items": {"type": "string"}},
                            "why_fit": {"type": "string"},
                        },
                        "required": ["product_id"],
                    },
                },
            },
            "required": ["answer", "recommendations"],
        },
        "strict": True,
    }


def _call_qwen_plus(
    *,
    messages: List[Dict[str, str]],
    timeout_s: float = 45.0,
) -> Dict[str, Any]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise serializers.ValidationError("Server is not configured: DASHSCOPE_API_KEY is missing")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body: Dict[str, Any] = {
        "model": QWEN_MODEL,
        "messages": messages,
        "stream": False,
        "response_format": {"type": "json_schema", "json_schema": _response_json_schema()},
    }

    try:
        resp = requests.post(
            DASHSCOPE_CHAT_COMPLETIONS_URL,
            headers=headers,
            json=body,
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        raise serializers.ValidationError(f"Upstream request failed: {exc}")

    if resp.status_code >= 400:
        # Try best-effort to include upstream error message.
        try:
            payload = resp.json()
        except Exception:
            payload = {"error": resp.text[:1000]}
        raise serializers.ValidationError(
            {"upstream_status": resp.status_code, "upstream_error": payload}
        )

    return resp.json()


def _extract_model_json(upstream: Dict[str, Any]) -> Dict[str, Any]:
    try:
        content = upstream["choices"][0]["message"]["content"]
    except Exception:
        raise serializers.ValidationError("Upstream response format unexpected")

    if not isinstance(content, str):
        raise serializers.ValidationError("Upstream content is not a string")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Some providers may still return already-structured content; accept dict.
        if isinstance(content, dict):
            return content
        raise serializers.ValidationError("Model did not return valid JSON")


def _merge_recommendations(
    *,
    candidates: Sequence[CandidateProduct],
    model_payload: Dict[str, Any],
) -> Dict[str, Any]:
    candidate_by_id = {p.id: p for p in candidates}

    answer = model_payload.get("answer")
    if not isinstance(answer, str):
        answer = ""

    recs_in = model_payload.get("recommendations")
    if not isinstance(recs_in, list):
        recs_in = []

    recs_out: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for rec in recs_in:
        if not isinstance(rec, dict):
            continue
        pid = rec.get("product_id")
        if not isinstance(pid, int) or pid in seen:
            continue
        cand = candidate_by_id.get(pid)
        if cand is None:
            continue
        seen.add(pid)

        highlights = rec.get("highlights")
        tradeoffs = rec.get("tradeoffs")
        why_fit = rec.get("why_fit")

        recs_out.append(
            {
                "product_id": cand.id,
                "name": cand.name,
                "model": cand.model,
                "price": str(cand.price),
                "stock": cand.stock,
                "highlights": highlights if isinstance(highlights, list) else [],
                "tradeoffs": tradeoffs if isinstance(tradeoffs, list) else [],
                "why_fit": why_fit if isinstance(why_fit, str) else "",
            }
        )

    return {"answer": answer, "recommendations": recs_out}


class AssistantChatView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AssistantChatThrottle]

    @swagger_auto_schema(
        operation_summary="电脑商城：基于商品库的 AI 推荐问答（qwen-plus）",
        request_body=AssistantChatRequestSerializer,
        responses={
            200: openapi.Response("OK", AssistantChatResponseSerializer),
            400: "Bad Request",
            429: "Too Many Requests",
            500: "Server Error",
        },
    )
    def post(self, request):
        req_ser = AssistantChatRequestSerializer(data=request.data)
        req_ser.is_valid(raise_exception=True)
        data = req_ser.validated_data

        message: str = data["message"].strip()
        budget_min = data.get("budget_min")
        budget_max = data.get("budget_max")
        limit: int = data.get("limit", 8)
        history: List[Dict[str, str]] = data.get("history") or []

        candidates = _get_candidate_products(
            budget_min=budget_min,
            budget_max=budget_max,
            limit=limit,
        )

        used_filters = {
            "budget_min": str(budget_min) if budget_min is not None else None,
            "budget_max": str(budget_max) if budget_max is not None else None,
            "limit": limit,
        }

        if not candidates:
            payload = {
                "answer": "当前商品库中没有符合预算区间的商品。你可以调整预算范围，或告诉我更具体的用途（办公/游戏/剪辑/便携等）。",
                "recommendations": [],
                "used_filters": used_filters,
            }
            return Response(payload, status=status.HTTP_200_OK)

        catalog = _build_catalog_block(candidates)

        system = (
            "你是电脑商城的导购助手。你只能使用 CATALOG 中给出的商品事实（id/name/model/price/stock/description）进行推荐与解释。"
            "如果用户询问的配置细节不在 description 里，必须明确说明‘商品库未提供该配置细节’，不要编造。"
            "请严格输出一个 JSON 对象，不要输出 Markdown/代码块。"
            "recommendations 里只返回来自 CATALOG 的 product_id，并给出简短理由（highlights/tradeoffs/why_fit）。"
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        # Keep short history to avoid token explosion.
        for h in history[-6:]:
            messages.append({"role": h["role"], "content": h["content"]})

        user_content = f"{catalog}\n\nUSER_QUESTION: {message}"
        messages.append({"role": "user", "content": user_content})

        upstream = _call_qwen_plus(messages=messages)
        model_payload = _extract_model_json(upstream)
        merged = _merge_recommendations(candidates=candidates, model_payload=model_payload)

        resp_payload = {
            "answer": merged["answer"],
            "recommendations": merged["recommendations"],
            "used_filters": used_filters,
        }

        # Validate shape for safety
        resp_ser = AssistantChatResponseSerializer(data=resp_payload)
        resp_ser.is_valid(raise_exception=True)

        return Response(resp_ser.data, status=status.HTTP_200_OK)
