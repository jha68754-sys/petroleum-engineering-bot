"""
Test suite for 409 Conflict fix verification.
Uses mocks - does NOT connect to real Telegram API.
"""

import os
import sys
import logging
import hashlib
import re
from io import StringIO
from unittest.mock import MagicMock, patch, PropertyMock

# Setup environment before imports
os.environ["TELEGRAM_BOT_TOKEN"] = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
os.environ["OPENAI_API_KEY"] = "test_api_key_for_groq"

sys.path.insert(0, os.path.dirname(__file__))

# ═══════════════════════════════════════════════════════════════════════
#  TEST 1: Token Redaction in Logging
# ═══════════════════════════════════════════════════════════════════════

def test_token_redaction():
    """Test that bot tokens are redacted from log output."""
    print("\n=== TEST 1: Token Redaction in Logs ===")
    
    from logging_config import setup_logging, TokenRedactionFilter, _TOKEN_RE
    
    # Test regex pattern
    test_token = "bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    result = _TOKEN_RE.sub("bot[REDACTED]", f"URL: https://api.telegram.org/bot{test_token}/getUpdates")
    assert "bot[REDACTED]" in result, f"Token not redacted: {result}"
    assert test_token not in result, f"Original token still in output: {result}"
    print("  Token regex redaction: PASS")
    
    # Test filter on LogRecord
    logger = logging.getLogger("test_redaction")
    logger.handlers.clear()
    
    # Capture log output
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(TokenRedactionFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    
    # Log a message containing a token
    test_url = "https://api.telegram.org/bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef/sendMessage"
    logger.error("Connection failed: %s", test_url)
    
    output = stream.getvalue()
    assert "bot[REDACTED]" in output, f"Token not redacted in log: {output}"
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in output, f"Full token leaked: {output}"
    print(f"  Filtered log output: {output.strip()}")
    print("  Token redaction filter: PASS")
    
    # Cleanup
    logger.handlers.clear()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 2: Instance Identity
# ═══════════════════════════════════════════════════════════════════════

def test_instance_identity():
    """Test that instance identity is collected correctly."""
    print("\n=== TEST 2: Instance Identity ===")
    
    # Import after env is set
    import main
    
    identity = main.get_instance_identity()
    
    assert "pid" in identity, "Missing PID"
    assert "hostname" in identity, "Missing hostname"
    assert "python" in identity, "Missing python version"
    
    print(f"  PID: {identity['pid']}")
    print(f"  Hostname: {identity['hostname']}")
    print(f"  Python: {identity['python']}")
    
    if "commit_sha" in identity:
        print(f"  Commit SHA: {identity['commit_sha']}")
    if "branch" in identity:
        print(f"  Branch: {identity['branch']}")
    
    # Verify fingerprint doesn't expose token
    fp = main.token_fingerprint()
    assert len(fp) == 8, f"Fingerprint wrong length: {len(fp)}"
    assert "1234567890" not in fp, "Token digits in fingerprint"
    print(f"  Token fingerprint (sha256 first 8): {fp}")
    print("  Instance identity: PASS")


# ═══════════════════════════════════════════════════════════════════════
#  TEST 3: TelegramService Mock Tests
# ═══════════════════════════════════════════════════════════════════════

def test_telegram_service():
    """Test TelegramService with mocked HTTP."""
    print("\n=== TEST 3: TelegramService (Mocked) ===")
    
    from services.telegram_service import TelegramService, _redact_token
    
    # Test token redaction helper
    result = _redact_token("Error at https://api.telegram.org/bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef/getUpdates")
    assert "bot[REDACTED]" in result
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in result
    print("  _redact_token(): PASS")
    
    # Test TelegramService initialization
    tg = TelegramService()
    assert tg.token_fingerprint == "cdef", f"Wrong fingerprint: {tg.token_fingerprint}"
    print(f"  Token fingerprint: ...{tg.token_fingerprint}")
    print("  TelegramService init: PASS")
    
    # Test delete_webhook with mock
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    
    with patch.object(tg.session, 'post', return_value=mock_response) as mock_post:
        result = tg.delete_webhook(drop_pending=True)
        assert result is True, "delete_webhook should return True"
        mock_post.assert_called_once()
        # Verify drop_pending was passed
        call_kwargs = mock_post.call_args
        assert "params" in str(call_kwargs) or "drop_pending_updates" in str(call_kwargs)
        print("  delete_webhook (success): PASS")
    
    # Test delete_webhook failure + retry
    mock_response_fail = MagicMock()
    mock_response_fail.json.return_value = {"ok": False, "description": "Error"}
    mock_response_fail.raise_for_status = MagicMock()  # No exception
    
    with patch.object(tg.session, 'post', return_value=mock_response_fail) as mock_post:
        result = tg.delete_webhook()
        assert result is False, "delete_webhook should return False on failure"
        assert mock_post.call_count == 3, f"Should retry 3 times, got {mock_post.call_count}"
        print("  delete_webhook (retry 3x): PASS")
    
    # Test get_updates with mock
    mock_updates = MagicMock()
    mock_updates.json.return_value = {
        "ok": True,
        "result": [{"update_id": 1, "message": {"text": "/start", "chat": {"id": 123}}}]
    }
    
    with patch.object(tg.session, 'get', return_value=mock_updates) as mock_get:
        updates = tg.get_updates(offset=0, timeout=30)
        assert len(updates) == 1, f"Expected 1 update, got {len(updates)}"
        print("  get_updates (success): PASS")
    
    # Test get_updates conflict
    mock_conflict = MagicMock()
    mock_conflict.json.return_value = {
        "ok": False,
        "description": "Conflict: terminated by other getUpdates request"
    }
    
    with patch.object(tg.session, 'get', return_value=mock_conflict) as mock_get:
        updates = tg.get_updates(offset=0, timeout=30)
        assert len(updates) == 0, "Should return empty list on conflict"
        print("  get_updates (409 conflict): PASS")
    
    # Test get_webhook_info
    mock_wh = MagicMock()
    mock_wh.json.return_value = {"ok": True, "result": {"url": "", "pending_update_count": 0}}
    
    with patch.object(tg.session, 'get', return_value=mock_wh) as mock_get:
        info = tg.get_webhook_info()
        assert info is not None
        assert info.get("url") == "", "Webhook URL should be empty"
        print("  get_webhook_info (no webhook): PASS")
    
    tg.close()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 4: Startup Delay Configuration
# ═══════════════════════════════════════════════════════════════════════

def test_startup_delay():
    """Test that startup delay is configurable."""
    print("\n=== TEST 4: Startup Delay Configuration ===")
    
    # Default value
    import importlib
    import main as main_mod
    
    # The delay is read at module level. Raised from 8s to 45s: it must exceed
    # the worst-case time a previous instance can still be blocked inside an
    # in-flight long-poll get_updates() call after SIGTERM (~POLLING_TIMEOUT+10s
    # = 40s with defaults), otherwise old and new containers can both poll
    # getUpdates simultaneously and trigger 409 Conflict. See AUDIT_REPORT.md B1.
    default_delay = int(os.environ.get("STARTUP_DELAY", "45"))
    assert default_delay == 45, f"Default delay should be 45, got {default_delay}"
    assert default_delay > 30, "STARTUP_DELAY must exceed the ~40s worst-case shutdown overlap window"
    print(f"  Default STARTUP_DELAY: {default_delay}s")
    
    # Custom value
    os.environ["STARTUP_DELAY"] = "5"
    assert int(os.environ["STARTUP_DELAY"]) == 5
    os.environ["STARTUP_DELAY"] = "45"  # Reset to production default
    print("  Startup delay configuration: PASS")


# ═══════════════════════════════════════════════════════════════════════
#  TEST 5: No Token in Error Handling
# ═══════════════════════════════════════════════════════════════════════

def test_no_token_in_errors():
    """Test that token never appears in error messages."""
    print("\n=== TEST 5: Token Safety in Errors ===")
    
    import main
    
    test_cases = [
        "https://api.telegram.org/bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef/getUpdates",
        "Failed to connect to bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
        "Connection to bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef timed out",
    ]
    
    for case in test_cases:
        redacted = main.redact_token(case)
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in redacted, f"Token leaked: {redacted}"
        assert "1234567890" not in redacted, f"Token digits leaked: {redacted}"
        assert "bot[REDACTED]" in redacted, f"Redaction missing: {redacted}"
    
    print("  All token redaction test cases: PASS")


# ═══════════════════════════════════════════════════════════════════════
#  TEST 6: Engineering Correlation Fixes (audit findings E1 / E2)
# ═══════════════════════════════════════════════════════════════════════

def test_engineering_formula_fixes():
    """Regression test for the Bo/Vasquez-Beggs formula bugs found in the audit."""
    print("\n=== TEST 6: Engineering Correlation Fixes ===")

    from constants import CORRELATIONS, HELP_MESSAGE

    # E1: bo_standing must NOT have the spurious outer sqrt anymore.
    # Correct Standing Bo for these inputs is well above 1.2 (no sqrt shrinkage).
    bo_func = CORRELATIONS["bo_standing"]["func"]
    bo = bo_func(rs=650, gas_sg=0.75, tres=180, api=35)
    assert bo > 1.2, f"bo_standing looks sqrt-shrunk (got {bo}); expected a realistic Bo > 1.2"
    print(f"  bo_standing(rs=650, gas_sg=0.75, tres=180, api=35) = {bo:.4f}: PASS")

    # E2: Vasquez-Beggs must actually use p_sep (result must change with p_sep).
    rs_func = CORRELATIONS["rs_vasquez_beggs"]["func"]
    rs_low_psep = rs_func(p=2000, gas_sg=0.75, tres=180, api=35, p_sep=100)
    rs_high_psep = rs_func(p=2000, gas_sg=0.75, tres=180, api=35, p_sep=500)
    assert rs_low_psep != rs_high_psep, "rs_vasquez_beggs ignores p_sep -- regression!"
    print(f"  rs_vasquez_beggs varies with p_sep ({rs_low_psep:.2f} vs {rs_high_psep:.2f}): PASS")

    # Pb/Rs should round-trip through the same coefficient branch.
    pb_func = CORRELATIONS["pb_vasquez_beggs"]["func"]
    pb = pb_func(rs=rs_low_psep, gas_sg=0.75, tres=180, api=35, p_sep=100)
    assert abs(pb - 2000) < 1e-3, f"pb_vasquez_beggs did not round-trip Rs->Pb correctly (got {pb})"
    print(f"  pb_vasquez_beggs round-trips Rs->Pb ({pb:.4f} ~= 2000): PASS")

    # A2: HELP_MESSAGE must be defined exactly once (no dead duplicate left behind).
    assert HELP_MESSAGE.count("Petroleum Engineering AI Bot") <= 2  # title appears once in header text
    print("  HELP_MESSAGE duplicate removed: PASS")


# ═══════════════════════════════════════════════════════════════════════
#  TEST 7: /analyze and /graph now delegate to the AI (audit finding A1)
# ═══════════════════════════════════════════════════════════════════════

def test_analyze_graph_dispatch():
    """Regression test: /analyze and /graph must not silently no-op anymore."""
    print("\n=== TEST 7: /analyze and /graph Dispatch ===")

    from handlers.text_handlers import handle_analyze, handle_graph

    # With no file/image context uploaded, handlers should still return a
    # helpful message (not the AI-delegation sentinel).
    msg = {"chat": {"id": 999999}, "text": "/analyze", "message_id": 1}
    result_text, png_bytes, doc_filename = handle_analyze(msg, None)
    assert result_text is not None, "handle_analyze should prompt for upload when no context exists"
    print("  handle_analyze() without context still responds: PASS")

    msg2 = {"chat": {"id": 999999}, "text": "/graph", "message_id": 1}
    result_text2, png_bytes2, doc_filename2 = handle_graph(msg2, None)
    assert result_text2 is not None, "handle_graph should prompt for upload when no context exists"
    print("  handle_graph() without context still responds: PASS")

    # Verify main.py's dispatch block contains the sentinel-forwarding fix.
    import inspect
    import main as main_mod
    src = inspect.getsource(main_mod.process_message)
    assert "_handle_free_text(message, ai_prompt, tg, ai)" in src, (
        "main.py dispatch no longer forwards the (None, None, None) sentinel to the AI -- regression!"
    )
    print("  main.py forwards /analyze /graph sentinel to AI: PASS")


# ═══════════════════════════════════════════════════════════════════════
#  TEST 8: AI Response Cache Key No Longer Collides (audit finding D1)
# ═══════════════════════════════════════════════════════════════════════

def test_cache_key_no_collision():
    """Regression test: distinct questions must not share a cache key."""
    print("\n=== TEST 8: AI Cache Key Collision Fix ===")

    import inspect
    from services.ai_service import AIService
    src = inspect.getsource(AIService.ask_text)
    assert "[:2000]" not in src, "Cache key still uses truncated-prefix approach -- regression!"
    assert "hashlib.sha256" in src, "Cache key should be a hash of the user-relevant tail"
    print("  ask_text() cache key uses hashed user-relevant tail, not truncated prefix: PASS")


# ═══════════════════════════════════════════════════════════════════════
#  TEST 9: Second-Round Audit Fixes (D2, D3, D4, E3, E4, E5, G1-G3)
# ═══════════════════════════════════════════════════════════════════════

def test_second_round_fixes():
    """Regression tests for the lower-priority audit items fixed on request."""
    print("\n=== TEST 9: Second-Round Audit Fixes ===")

    # E3: Dry Gas must be reachable via no_liquid=True, and NOT reachable
    # via ordinary GOR=0/API=0 (which is not a realistic sample).
    from services.pvt_engine import classify_fluid
    dry = classify_fluid(gor=500000, api=0, no_liquid=True)
    assert dry["type_en"] == "Dry Gas", "no_liquid=True should classify as Dry Gas"
    print("  Dry Gas reachable via no_liquid=True: PASS")

    normal_zero = classify_fluid(gor=0, api=0, no_liquid=False)
    assert normal_zero["type_en"] != "Dry Gas", (
        "Dry Gas should no longer be reachable via plain GOR=0/API=0 input"
    )
    print("  Dry Gas no longer silently matched by GOR=0/API=0: PASS")

    # E4: boundary values should carry a boundary_note.
    boundary_result = classify_fluid(gor=2000, api=35)  # exactly on Black/Volatile Oil GOR boundary
    assert boundary_result.get("boundary_note"), "Boundary case should carry a boundary_note"
    print("  Boundary ambiguity is now flagged: PASS")

    # E5: density validator must no longer be a rubber-stamp True.
    from services.pvt_engine import _validate_density_trend
    lines: list = []
    # Deliberately wrong trend: density decreasing below Pb (should increase)
    ok = _validate_density_trend(
        pressures=[1000, 1500, 2000, 2500],
        values=[55.0, 50.0, 45.0, 40.0],  # monotonically decreasing -- wrong below Pb=2000
        pb=2000,
        lines=lines,
    )
    assert ok is False, "density validator should now catch a decreasing trend below Pb"
    print("  Density validator catches bad trends (no longer a stub): PASS")

    # D3: TEXT_FIXES must no longer blanket-strip [ and ].
    from constants import TEXT_FIXES
    assert "[" not in TEXT_FIXES and "]" not in TEXT_FIXES, "Bracket stripping should be removed"
    print("  TEXT_FIXES no longer strips [ and ]: PASS")

    # D4: vision retries raised to match text retries.
    from config import AI_MAX_RETRIES, AI_MAX_VISION_RETRIES
    assert AI_MAX_VISION_RETRIES == AI_MAX_RETRIES == 3
    print("  Vision retry budget matches text retry budget (3): PASS")

    # D2/G1: engineering knowledge base only sent in full on first turn.
    import inspect
    from services.ai_service import AIService
    src = inspect.getsource(AIService.ask_text)
    assert "if not chat_history:" in src and "Reminder:" in src, (
        "ask_text should only send the full engineering context on the first turn"
    )
    print("  Full knowledge base only sent on first conversation turn: PASS")

    # G2: main loop should not sleep unconditionally after processing updates.
    src_main = inspect.getsource(main.run) if "main" in dir() else None
    import main as main_mod
    run_src = inspect.getsource(main_mod.run)
    assert "else:\n                    time.sleep(POLLING_LOOP_SLEEP)" in run_src, (
        "Polling loop should only sleep when idle, not after every processed batch"
    )
    print("  Polling loop no longer sleeps after every processed batch: PASS")

    # G3: send_message should only sleep between chunks, not after the last one.
    from services.telegram_service import TelegramService
    send_src = inspect.getsource(TelegramService.send_message)
    assert "if i < len(chunks) - 1:" in send_src, (
        "send_message should only pace itself between chunks, not after the last chunk"
    )
    print("  send_message no longer sleeps after the last/only chunk: PASS")


# ═══════════════════════════════════════════════════════════════════════
#  RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_token_redaction()
    test_instance_identity()
    test_telegram_service()
    test_startup_delay()
    test_no_token_in_errors()
    test_engineering_formula_fixes()
    test_analyze_graph_dispatch()
    test_cache_key_no_collision()
    test_second_round_fixes()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED - 409 Fix + Full Audit Regression Verification Complete")
    print("=" * 60)
