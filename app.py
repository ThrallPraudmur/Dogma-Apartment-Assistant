"""Streamlit entry point. Run: streamlit run app.py"""
import json
import os
import time
from pathlib import Path

import streamlit as st

from agent import AgentError, DEFAULT_MODEL, respond
from catalog import Catalog, money

st.set_page_config(page_title="Квартиры DOGMA · Подбор", page_icon="🏡", layout="centered")


@st.cache_resource
def load_catalog(db_mtime, json_mtime):
    return Catalog()


def setting(name, default=""):
    if os.environ.get(name):
        return os.environ[name]
    try:
        return st.secrets.get(name, default)
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


def filter_text(filters):
    labels = []
    if "project" in filters:
        labels.append(filters["project"])
    if "budget_min" in filters:
        labels.append("от " + money(filters["budget_min"]))
    if "budget_max" in filters:
        labels.append("до " + money(filters["budget_max"]))
    if "area_min" in filters:
        labels.append(f"от {filters['area_min']:g} м²")
    if "area_max" in filters:
        labels.append(f"до {filters['area_max']:g} м²")
    if "rooms" in filters:
        labels.append("студия" if filters["rooms"] == 0 else f"комнат: {filters['rooms']}")
    return " · ".join(labels) or "Условия пока не заданы"


def render_result(result, index):
    if result.get("needs_clarification"):
        st.write(result["explanation"])
        if result.get("project_candidates"):
            st.caption(" · ".join(result["project_candidates"]))
    elif not result["answer"]:
        st.info(result["explanation"])
    else:
        st.write(f"Найдено **{result['total_matches']}**. Показываю **{len(result['answer'])}**.")
        st.caption(result["explanation"])
        for rank, lot in enumerate(result["answer"], 1):
            with st.container(border=True):
                title = "Студия" if lot["rooms"] == 0 else f"{lot['rooms']}-комнатная"
                st.markdown(f"**{rank}. {lot['project']} · {title}**")
                a, b, c = st.columns(3)
                a.metric("Цена", money(lot["price_rub"]))
                b.metric("Площадь", f"{lot['area_m2']:g} м²")
                c.metric("Этаж", f"{lot['floor']} / {lot['floors_total']}")
                st.caption(lot["address"] or "")
                st.write(lot["explanation"])
                if lot["sale_price_rub"] and lot["base_price_rub"] > lot["price_rub"]:
                    st.caption(f"Цена по акции. Базовая: {money(lot['base_price_rub'])}. Условия уточняйте на странице лота.")
                st.link_button("Открыть квартиру ↗", lot["url"])
    with st.expander("Ответ в JSON"):
        st.json(result)
        st.download_button("Скачать JSON", json.dumps(result, ensure_ascii=False, indent=2), file_name="dogma-result.json", mime="application/json", key=f"download_{index}")


root = Path(__file__).parent
try:
    catalog = load_catalog((root / "data/apartments.sqlite").stat().st_mtime_ns, (root / "data/apartments.json").stat().st_mtime_ns)
except (OSError, ValueError) as exc:
    st.error(f"Не удалось загрузить каталог: {exc}")
    st.stop()

for key, value in (("messages", []), ("filters", {}), ("last_request", 0.0)):
    if key not in st.session_state:
        st.session_state[key] = value

with st.sidebar:
    st.markdown("### DOGMA / подбор")
    st.caption("Демонстрационный помощник по квартирам")
    mode = st.radio("Способ поиска", ["AI-чат", "Фильтры"])
    limit = st.select_slider("Показать вариантов", options=[3, 5], value=3)
    st.divider()
    st.markdown("**Текущие условия**")
    st.write(filter_text(st.session_state.filters))
    if st.button("Новый поиск", use_container_width=True):
        st.session_state.messages = []
        st.session_state.filters = {}
        st.session_state.last_request = 0.0
        st.rerun()
    with st.expander(f"Жилые комплексы · {len(catalog.projects)}"):
        for project in catalog.projects:
            st.write(project)
    with st.expander("О данных"):
        st.write(f"Квартир в снимке: {catalog.count:,}".replace(",", " "))
        st.write("Собрано: " + catalog.metadata["finished_at"][:16].replace("T", " ") + " UTC")
        if not catalog.metadata["complete"]:
            st.caption("Каталог менялся при сборе; полная согласованность снимка не подтверждена.")
        st.caption("Собраны лоты со статусом 2 из публичного каталога. Цены и наличие проверяйте по ссылке квартиры.")
    configured_key = setting("OPENROUTER_API_KEY")
    with st.expander("Подключение AI", expanded=not bool(configured_key)):
        entered_key = st.text_input("Ключ OpenRouter", type="password", key="api_key_input", help="Не сохраняется в файлы. Для публикации используйте Secrets.")
        st.caption("Ключ настроен на сервере." if configured_key else "Без ключа доступен поиск через фильтры.")
        st.caption("Бесплатная модель: " + setting("OPENROUTER_MODEL", DEFAULT_MODEL))
    api_key = entered_key or configured_key

st.title("Квартира под ваш запрос")
st.caption("Опишите бюджет, площадь и ЖК — или задайте условия через фильтры.")

if not st.session_state.messages:
    st.markdown("Например: **«Найди квартиру в ГРЕЙД до 7 млн рублей, от 30 м²»**")
    st.caption("Можно продолжить: «А теперь до 8 млн» или «Покажи только студии».")

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message.get("result"):
            render_result(message["result"], index)
        elif message.get("error"):
            st.error(message["content"])
        else:
            st.write(message["content"])

if mode == "Фильтры":
    with st.form("manual_search"):
        st.markdown("#### Задайте условия")
        project = st.selectbox("ЖК", ["Любой ЖК", *catalog.projects])
        rooms = st.selectbox("Комнаты", ["Любое количество", "Студия", "1", "2", "3", "4"])
        col1, col2 = st.columns(2)
        budget = col1.number_input("Бюджет до, ₽", min_value=0, value=7_000_000, step=100_000, help="0 — без ограничения")
        area = col2.number_input("Площадь от, м²", min_value=0.0, value=30.0, step=1.0)
        submitted = st.form_submit_button("Подобрать квартиры", type="primary", use_container_width=True)
    if submitted:
        filters = {}
        if project != "Любой ЖК":
            filters["project"] = project
        if rooms != "Любое количество":
            filters["rooms"] = 0 if rooms == "Студия" else int(rooms)
        if budget:
            filters["budget_max"] = budget
        if area:
            filters["area_min"] = area
        result = catalog.search(filters, limit)
        st.session_state.filters = result["filters"]
        st.session_state.messages.extend([{"role": "user", "content": "Поиск по фильтрам: " + filter_text(filters)}, {"role": "assistant", "content": result["explanation"], "result": result}])
        st.session_state.messages = st.session_state.messages[-30:]
        st.rerun()
else:
    if not api_key:
        st.info("Для AI-чата добавьте ключ OpenRouter в боковой панели. Поиск по фильтрам работает без ключа.")
    query = st.chat_input("Например: студия до 7 млн рублей, от 25 м²", max_chars=4000, disabled=not bool(api_key))
    if query:
        history = list(st.session_state.messages)
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.write(query)
        with st.chat_message("assistant"):
            try:
                if time.monotonic() - st.session_state.last_request < 2:
                    raise AgentError("Подождите пару секунд перед следующим запросом.")
                st.session_state.last_request = time.monotonic()
                with st.spinner("Разбираю запрос и подбираю квартиры…"):
                    result = respond(query, st.session_state.filters, history, catalog, api_key, limit, setting("OPENROUTER_MODEL", DEFAULT_MODEL))
                if not result["needs_clarification"]:
                    st.session_state.filters = result["filters"]
                st.session_state.messages.append({"role": "assistant", "content": result["explanation"], "result": result})
            except (AgentError, ValueError) as exc:
                st.session_state.messages.append({"role": "assistant", "content": str(exc), "error": True})
        st.session_state.messages = st.session_state.messages[-30:]
        st.rerun()

st.caption("Учебный проект на данных dogma.ru. Перед покупкой уточните цену и доступность у застройщика.")
