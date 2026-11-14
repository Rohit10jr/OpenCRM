from core.translate import _


def test_message_template_marker_returns_text_unchanged():
    template = "DocType {0} not found"
    assert _(template) == template
