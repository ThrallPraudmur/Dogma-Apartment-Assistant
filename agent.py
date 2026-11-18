"""OpenRouter extracts changes; application owns validation and filter merging."""
import json
from pathlib import Path
import requests
from catalog import FIELDS, validate_filters

DEFAULT_MODEL = "inclusionai/ling-3.2-flash:free"


class AgentError(Exception):
    pass


def validate_extraction(data):
    keys = {"filters", "remove_filters", "reset_filters", "needs_clarification", "clarification_question"}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError("Некорректная структура ответа модели.")
    validate_filters(data["filters"])
    if type(data["reset_filters"]) is not bool or type(data["needs_clarification"]) is not bool:
        raise ValueError("Некорректные флаги ответа модели.")
    remove = data["remove_filters"]
    if not isinstance(remove, list) or any(not isinstance(k, str) or k not in FIELDS for k in remove):
        raise ValueError("Некорректный список удаляемых фильтров.")
    if set(remove) & set(data["filters"]):
        raise ValueError("Противоречивое изменение фильтров.")
    question = data["clarification_question"]
    if data["needs_clarification"]:
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            raise ValueError("Отсутствует вопрос для уточнения.")
    elif question is not None:
        raise ValueError("Неожиданный вопрос для уточнения.")
    return data


def merge_filters(current, extraction):
    validate_filters(current)
    validate_extraction(extraction)
    if extraction["needs_clarification"]:
        return dict(current)
    merged = {} if extraction["reset_filters"] else dict(current)
    for key in extraction["remove_filters"]:
        merged.pop(key, None)
    merged.update(extraction["filters"])
    return validate_filters(merged)


def extract(query, current, history, projects, api_key, model=DEFAULT_MODEL):
    if not api_key:
        raise AgentError("Для чата настройте ключ OpenRouter в боковой панели или Secrets.")
    if not model.endswith(":free") and model != "openrouter/free":
        raise AgentError("В этом приложении разрешены только бесплатные модели.")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 4000:
        raise AgentError("Введите запрос длиной от 1 до 4000 символов.")
    validate_filters(current)
    prompt = (Path(__file__).parent / "schemas/chat-prompt.txt").read_text(encoding="utf-8-sig")
    messages = [{"role": "system", "content": prompt}, {"role": "system", "content": json.dumps({"current_filters": current, "projects": projects}, ensure_ascii=False)}]
    messages.extend({"role": m["role"], "content": m["content"][:4000]} for m in history[-12:] if m["role"] in ("user", "assistant"))
    messages.append({"role": "user", "content": query})
    for attempt in range(2):
        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "temperature": 0, "max_tokens": 2048, "response_format": {"type": "json_object"}, "messages": messages}, timeout=(10, 45))
        except requests.RequestException:
            raise AgentError("OpenRouter не ответил вовремя. Повторите запрос; текущие условия сохранены.") from None
        if response.status_code != 200:
            hints = {401: "Ключ OpenRouter недействителен.", 402: "OpenRouter ограничил доступ по балансу или лимиту ключа.", 403: "OpenRouter запретил доступ к модели. Проверьте настройки аккаунта.", 429: "Бесплатная модель сейчас перегружена или достигнут лимит. Повторите позже."}
            raise AgentError(hints.get(response.status_code, f"OpenRouter временно недоступен (HTTP {response.status_code}). Повторите позже."))
        try:
            payload = response.json()
            if payload.get("error"):
                raise AgentError("OpenRouter вернул ошибку модели. Повторите позже.")
            content = payload["choices"][0]["message"]["content"]
            data = validate_extraction(json.loads(content))
            # Check cross-field constraints against the existing state before committing.
            merge_filters(current, data)
            return data, {"model": payload.get("model", model), "cost": payload.get("usage", {}).get("cost")}
        except (ValueError, KeyError, IndexError, TypeError):
            if attempt:
                raise AgentError("Модель не смогла сформировать корректные параметры. Переформулируйте запрос; прежние условия сохранены.") from None
            messages.append({"role": "user", "content": "Предыдущий ответ имел неверную структуру или противоречивые диапазоны. Верни корректный JSON по инструкции; при неоднозначности задай уточнение."})
    raise AgentError("Не удалось обработать запрос.")


def respond(query, current, history, catalog, api_key, limit=3, model=DEFAULT_MODEL):
    data, meta = extract(query, current, history, catalog.projects, api_key, model)
    if data["needs_clarification"]:
        return {"filters": dict(current), "answer": [], "explanation": data["clarification_question"], "needs_clarification": True, "total_matches": 0, **meta}
    filters = merge_filters(current, data)
    return {**catalog.search(filters, limit), **meta}
