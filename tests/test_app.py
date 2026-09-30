"""
The whole Streamlit app, run headless with a fake Supabase and a fake LLM.
Covers: login gate, register, asking, saved chats, follow-up context, rename,
delete, the 30-a-day limit, that one user can't see another user's chats, the
table/chart view (default view, per-answer switch, old saved charts), the settings
dialog (saved to the user's account) and the suggested questions.
"""
import pytest
from streamlit.testing.v1 import AppTest

from agent import llm
from services.auth import DEFAULT_VIEW_KEY
from services import auth
from tests import fake_supabase
from tests.test_pipeline import FakeLLM, q

QUESTIONS = {
    "What was revenue in FY24?": q("value", ["net_revenue"], [{"type": "fiscal_year", "value": "FY24"}]),
    "and FY23?": q("value", ["net_revenue"], [{"type": "fiscal_year", "value": "FY23"}]),
    "Forecast revenue for the next 3 months": q("forecast", ["net_revenue"], horizon=3),
}


@pytest.fixture
def app(monkeypatch):
    fake_supabase.reset()
    # Fake keys for the fake Supabase. Patched directly (not via environment variables) because
    # get_secret() reads .streamlit/secrets.toml first, and your real keys must never reach the tests.
    fake_keys = {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_ANON_KEY": "anon-key",
                 "SUPABASE_SERVICE_KEY": "service-key"}
    monkeypatch.setattr(auth, "get_secret", lambda name: fake_keys[name])
    monkeypatch.setattr(auth, "create_client", fake_supabase.create_client)
    auth.admin_client.clear()
    fake = FakeLLM(QUESTIONS, recs=["Plan stock ahead of the winter peak."] * 100)
    monkeypatch.setattr(llm, "chat", fake)
    at = AppTest.from_file("../app.py", default_timeout=60)
    return at


def register(at, name="UT", email="ut@example.com", password="secret123"):
    at.run()
    at.text_input(key="reg_email").set_value(email)
    at.text_input(key="reg_pw").set_value(password)
    [t for t in at.text_input if t.label == "Your name"][0].set_value(name)
    [b for b in at.button if b.label == "Create account"][0].click().run()
    return at


def ask(at, text):
    at.chat_input[0].set_value(text).run()
    assert not at.exception, at.exception
    return at


def test_login_gate_then_register(app):
    app.run()
    assert any("bUlleTin" in m.value for m in app.markdown)
    assert len(app.chat_input) == 0                     # no chat before login
    register(app)
    assert any("UT" in m.value and "Good" in m.value for m in app.markdown)


def test_wrong_password_shows_friendly_error(app):
    register(app)
    [b for b in app.sidebar.button if b.label == "Log out"][0].click().run()
    [t for t in app.text_input if t.label == "Email"][0].set_value("ut@example.com")
    [t for t in app.text_input if t.label == "Password"][0].set_value("wrong-pass")
    [b for b in app.button if b.label == "Log in"][0].click().run()
    assert any("Wrong email or password" in e.value for e in app.error)


def test_chat_is_saved_and_follow_up_has_context(app):
    register(app)
    ask(app, "What was revenue in FY24?")
    chats = fake_supabase.DB["chats"]
    assert len(chats) == 1 and chats[0]["title"] == "What was revenue in FY24?"
    assert [m["role"] for m in fake_supabase.DB["messages"]] == ["user", "assistant"]
    assert "₹2.07 Cr" in fake_supabase.DB["messages"][1]["response"]["explanation"]
    ask(app, "and FY23?")
    assert len(fake_supabase.DB["chats"]) == 1          # same chat, not a new one
    assert len(fake_supabase.DB["messages"]) == 4
    assert any(b.label == "What was revenue in FY24?" for b in app.sidebar.button)


def charts(at):
    return at.get("vega_lite_chart")


def answer_key(index: int) -> str:
    return f"{fake_supabase.DB['chats'][0]['id']}-{index}"


def test_forecast_answer_renders_with_chart(app):
    register(app)
    ask(app, "Forecast revenue for the next 3 months")
    saved = fake_supabase.DB["messages"][1]["response"]
    assert saved["chart"]["series"][1]["name"] == "Forecast"          # legacy field, still sent for React
    assert saved["chart_spec"]["$schema"].endswith("/v6.json")          # new fields are saved too
    assert saved["chart_table"]["columns"][0]["label"] == "Month"
    assert len(app.expander) == 1                       # Details section


def test_answers_open_in_table_view_and_switch_to_chart(app):
    register(app)
    ask(app, "Forecast revenue for the next 3 months")
    view = f"view-{answer_key(1)}"
    assert app.session_state[view] == "table"
    assert len(charts(app)) == 0 and len(app.get("button_group")) == 1
    tables_before = len(app.dataframe)                  # table view + the Details "Numbers" table

    app.session_state[view] = "chart"
    app.run()
    assert not app.exception, app.exception
    assert len(charts(app)) == 1 and len(app.dataframe) == tables_before - 1


def open_settings(at):
    at.button(key="open-settings").click().run()
    assert not at.exception, at.exception


def test_settings_dialog_saves_default_view_to_the_account(app):
    register(app)
    open_settings(app)
    toggles = {t.label: t.disabled for t in app.toggle}
    assert toggles == {"Add to dashboard": True, "Customise dashboard": True}   # placeholders
    app.button_group(key="settings-view").set_value("chart").run()
    assert not app.exception, app.exception
    assert fake_supabase.USERS["ut@example.com"]["data"]["settings"] == {DEFAULT_VIEW_KEY: "chart"}
    assert fake_supabase.USERS["ut@example.com"]["data"]["name"] == "UT"      # name kept

    ask(app, "Forecast revenue for the next 3 months")
    assert len(charts(app)) == 1                         # opens as a chart now
    assert len(app.get("button_group")) == 1             # and the switch is still there


def test_saved_setting_comes_back_after_logging_in_again(app):
    register(app)
    open_settings(app)
    app.button_group(key="settings-view").set_value("chart").run()
    [b for b in app.sidebar.button if b.label == "Log out"][0].click().run()
    [t for t in app.text_input if t.label == "Email"][0].set_value("ut@example.com")
    [t for t in app.text_input if t.label == "Password"][0].set_value("secret123")
    [b for b in app.button if b.label == "Log in"][0].click().run()
    assert app.session_state[DEFAULT_VIEW_KEY] == "chart"


def test_suggested_question_is_asked(app):
    register(app)
    app.button(key="suggest-1").click().run()          # "Forecast revenue for the next 3 months"
    assert not app.exception, app.exception
    assert [m["role"] for m in fake_supabase.DB["messages"]] == ["user", "assistant"]
    assert fake_supabase.DB["messages"][0]["content"] == "Forecast revenue for the next 3 months"


def test_old_saved_chart_still_renders(app):
    """Messages saved before chart_spec existed only have the old `chart` dict."""
    register(app)
    ask(app, "What was revenue in FY24?")
    old = dict(fake_supabase.DB["messages"][1])
    old.update(id="old-msg", created_at=fake_supabase._now_iso(), content="old answer", response={
        "route_decision": "metric", "found": True, "confidence": "High", "explanation": "old answer",
        "chart": {"style": "line", "title": "Net revenue: actual and forecast", "unit": "inr",
                  "x_axis_data": ["2024-11", "2024-12", "2025-01"],
                  "series": [{"name": "Actual", "values": [2.6e6, 2.7e6, None]},
                             {"name": "Forecast", "values": [None, 2.7e6, 2.4e6]}]}})
    fake_supabase.DB["messages"].append(old)
    app.run()
    assert not app.exception, app.exception
    assert app.session_state[f"view-{answer_key(2)}"] == "table"
    app.session_state[f"view-{answer_key(2)}"] = "chart"
    app.run()
    assert not app.exception, app.exception
    assert len(charts(app)) == 1


def test_rename_and_delete(app):
    register(app)
    ask(app, "What was revenue in FY24?")
    chat_id = fake_supabase.DB["chats"][0]["id"]
    app.text_input(key=f"title-{chat_id}").set_value("FY24 revenue")
    app.button(key=f"save-{chat_id}").click().run()
    assert fake_supabase.DB["chats"][0]["title"] == "FY24 revenue"
    app.checkbox(key=f"sure-{chat_id}").check().run()
    app.button(key=f"del-{chat_id}").click().run()
    assert fake_supabase.DB["chats"] == [] and fake_supabase.DB["messages"] == []


def test_daily_limit_blocks_the_31st_question(app):
    register(app)
    uid = fake_supabase.USERS["ut@example.com"]["id"]
    for _ in range(30):
        fake_supabase.DB["usage"].append({"user_id": uid, "created_at": fake_supabase._now_iso()})
    ask(app, "What was revenue in FY24?")
    assert any("30 questions" in w.value for w in app.warning)
    assert fake_supabase.DB["messages"] == []           # nothing was asked or saved


def test_users_cannot_see_each_others_chats(app):
    register(app, name="A", email="a@example.com")
    ask(app, "What was revenue in FY24?")
    [b for b in app.sidebar.button if b.label == "Log out"][0].click().run()
    register(app, name="B", email="b@example.com")
    assert not any(b.label == "What was revenue in FY24?" for b in app.sidebar.button)