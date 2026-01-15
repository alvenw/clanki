"""Tests for render/html.py - HTML to terminal text conversion."""

from pathlib import Path

from clanki.render.html import (
    RenderMode,
    is_cloze_card,
    render_html_to_styled_segments,
    render_html_to_text,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestBasicTags:
    """Tests for basic HTML tag handling."""

    def test_div_produces_newline(self):
        """div tags should produce newlines."""
        result = render_html_to_text("<div>Hello</div><div>World</div>")
        assert "Hello" in result
        assert "World" in result
        # Content should be separated
        assert "HelloWorld" not in result

    def test_paragraph_produces_newline(self):
        """p tags should produce newlines."""
        result = render_html_to_text("<p>First</p><p>Second</p>")
        assert "First" in result
        assert "Second" in result

    def test_br_produces_newline(self):
        """br tags should produce newlines."""
        result = render_html_to_text("Line 1<br>Line 2")
        lines = result.split("\n")
        assert len(lines) >= 2

    def test_basic_fixture(self):
        """Test rendering of basic.html fixture."""
        html = (FIXTURES_DIR / "basic.html").read_text()
        result = render_html_to_text(html)

        assert "Hello World" in result
        assert "This is a paragraph" in result
        assert "Line after break" in result


class TestWhitespaceNormalization:
    """Tests for whitespace handling."""

    def test_collapses_multiple_spaces(self):
        """Multiple spaces should be collapsed to single space."""
        result = render_html_to_text("<div>Hello    World</div>")
        assert "Hello World" in result
        assert "    " not in result

    def test_strips_trailing_whitespace_from_lines(self):
        """Trailing whitespace from lines should be stripped."""
        result = render_html_to_text("<div>Content   </div>")
        # Lines should not have trailing spaces
        for line in result.split("\n"):
            assert not line.endswith(" "), f"Line has trailing space: {repr(line)}"
        assert "Content" in result

    def test_preserves_paragraph_breaks(self):
        """Paragraph breaks should be preserved."""
        result = render_html_to_text("<p>Para 1</p><p>Para 2</p>")
        assert "Para 1" in result
        assert "Para 2" in result


class TestSkipTags:
    """Tests for style and script tag skipping."""

    def test_style_content_skipped(self):
        """Content inside style tags should be removed."""
        result = render_html_to_text("<style>.card { color: red; }</style><div>Visible</div>")
        assert "color: red" not in result
        assert ".card" not in result
        assert "Visible" in result

    def test_script_content_skipped(self):
        """Content inside script tags should be removed."""
        result = render_html_to_text('<script>alert("hidden");</script><div>Visible</div>')
        assert "alert" not in result
        assert "hidden" not in result
        assert "Visible" in result

    def test_skip_tags_fixture(self):
        """Test skip_tags.html fixture."""
        html = (FIXTURES_DIR / "skip_tags.html").read_text()
        result = render_html_to_text(html)

        assert "font-size" not in result
        assert "console.log" not in result
        assert "Visible content" in result


class TestMediaTags:
    """Tests for media tag handling."""

    def test_anki_play_tag_conversion(self):
        """[anki:play:a:N] should convert to [audio: N]."""
        result = render_html_to_text("[anki:play:a:0]")
        assert "[audio: 0]" in result

    def test_anki_play_q_tag_conversion(self):
        """[anki:play:q:N] should also convert to [audio: N]."""
        result = render_html_to_text("[anki:play:q:1]")
        assert "[audio: 1]" in result

    def test_sound_tag_conversion(self):
        """[sound:filename] should convert to [audio: filename]."""
        result = render_html_to_text("[sound:example.mp3]")
        assert "[audio: example.mp3]" in result

    def test_image_tag_conversion(self):
        """img tags should convert to [image: filename]."""
        result = render_html_to_text('<img src="photo.jpg">')
        assert "[image: photo.jpg]" in result

    def test_image_with_path(self):
        """img src with path should extract just filename."""
        result = render_html_to_text('<img src="/path/to/image.png">')
        assert "[image: image.png]" in result

    def test_media_fixture(self):
        """Test media.html fixture."""
        html = (FIXTURES_DIR / "media.html").read_text()
        result = render_html_to_text(html)

        assert "[audio: 0]" in result
        assert "[audio: example.mp3]" in result
        assert "[image: image.jpg]" in result


class TestRubyFurigana:
    """Tests for ruby/furigana handling."""

    def test_ruby_produces_combined_format(self):
        """Ruby text should produce base(reading) format."""
        result = render_html_to_text("<ruby>漢字<rt>かんじ</rt></ruby>")
        assert "漢字(かんじ)" in result

    def test_ruby_preserves_surrounding_text(self):
        """Text around ruby elements should be preserved."""
        result = render_html_to_text("私は<ruby>日本語<rt>にほんご</rt></ruby>を勉強")
        assert "私は" in result
        assert "日本語(にほんご)" in result
        assert "を勉強" in result

    def test_ruby_fixture(self):
        """Test ruby.html fixture."""
        html = (FIXTURES_DIR / "ruby.html").read_text()
        result = render_html_to_text(html)

        assert "漢字(かんじ)" in result
        assert "日本語(にほんご)" in result
        assert "を読む" in result
        assert "を勉強しています" in result

    def test_ruby_without_rt(self):
        """Ruby without rt should just output base text."""
        result = render_html_to_text("<ruby>漢字</ruby>")
        assert "漢字" in result
        assert "(" not in result

    def test_multiple_ruby_elements(self):
        """Multiple ruby elements should all be converted."""
        result = render_html_to_text(
            "<ruby>東<rt>とう</rt></ruby><ruby>京<rt>きょう</rt></ruby>"
        )
        assert "東(とう)" in result
        assert "京(きょう)" in result


class TestHtmlEntities:
    """Tests for HTML entity decoding."""

    def test_decodes_common_entities(self):
        """Common HTML entities should be decoded."""
        result = render_html_to_text("&lt;tag&gt; &amp; &quot;quotes&quot;")
        assert "<tag>" in result
        assert "&" in result
        assert '"quotes"' in result

    def test_decodes_numeric_entities(self):
        """Numeric HTML entities should be decoded."""
        result = render_html_to_text("&#60;&#62;")  # < and >
        assert "<>" in result

    def test_decodes_nbsp(self):
        """Non-breaking space should be handled."""
        result = render_html_to_text("Hello&nbsp;World")
        # nbsp becomes regular space after normalization
        assert "Hello" in result
        assert "World" in result


class TestListFormatting:
    """Tests for list element handling."""

    def test_unordered_list_with_bullets(self):
        """ul/li should produce bulleted list."""
        result = render_html_to_text("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_nested_list_indentation(self):
        """Nested lists should be indented."""
        result = render_html_to_text(
            "<ul><li>Outer</li><ul><li>Inner</li></ul></ul>"
        )
        lines = result.split("\n")
        # Find the lines with items
        outer_line = next((l for l in lines if "Outer" in l), "")
        inner_line = next((l for l in lines if "Inner" in l), "")
        # Inner should have more leading space
        assert inner_line.startswith("  ") or "  -" in inner_line


class TestEmptyInput:
    """Tests for edge cases."""

    def test_empty_string(self):
        """Empty input should return empty string."""
        result = render_html_to_text("")
        assert result == ""

    def test_whitespace_only(self):
        """Whitespace-only input should return empty string."""
        result = render_html_to_text("   \n\n   ")
        assert result == ""


class TestClozeDetection:
    """Tests for cloze card detection."""

    def test_detects_cloze_span(self):
        """Should detect cloze span with class attribute."""
        html = '<div>The answer is <span class="cloze">42</span>.</div>'
        assert is_cloze_card(html) is True

    def test_detects_cloze_with_other_classes(self):
        """Should detect cloze even with other classes."""
        html = '<span class="highlight cloze active">answer</span>'
        assert is_cloze_card(html) is True

    def test_no_cloze_returns_false(self):
        """Should return False for non-cloze HTML."""
        html = "<div>Regular content without cloze</div>"
        assert is_cloze_card(html) is False

    def test_empty_html_returns_false(self):
        """Should return False for empty HTML."""
        assert is_cloze_card("") is False
        assert is_cloze_card(None) is False  # type: ignore

    def test_cloze_fixture(self):
        """Test cloze detection with fixture file."""
        html = (FIXTURES_DIR / "cloze.html").read_text()
        assert is_cloze_card(html) is True


class TestClozeRendering:
    """Tests for cloze deletion rendering."""

    def test_question_mode_shows_placeholder(self):
        """In question mode, cloze content should be replaced with [...]."""
        html = '<div>The answer is <span class="cloze">42</span>.</div>'
        result = render_html_to_text(html, mode=RenderMode.QUESTION)
        assert "[...]" in result
        assert "42" not in result
        assert "The answer is" in result

    def test_answer_mode_shows_content(self):
        """In answer mode, cloze content should be visible."""
        html = '<div>The answer is <span class="cloze">42</span>.</div>'
        result = render_html_to_text(html, mode=RenderMode.ANSWER)
        assert "42" in result
        assert "[...]" not in result
        assert "The answer is" in result

    def test_multiple_cloze_question_mode(self):
        """Multiple cloze deletions should all show [...] in question mode."""
        html = '<span class="cloze">Paris</span> is the capital of <span class="cloze">France</span>.'
        result = render_html_to_text(html, mode=RenderMode.QUESTION)
        assert result.count("[...]") == 2
        assert "Paris" not in result
        assert "France" not in result

    def test_multiple_cloze_answer_mode(self):
        """Multiple cloze deletions should all be visible in answer mode."""
        html = '<span class="cloze">Paris</span> is the capital of <span class="cloze">France</span>.'
        result = render_html_to_text(html, mode=RenderMode.ANSWER)
        assert "Paris" in result
        assert "France" in result
        assert "[...]" not in result

    def test_cloze_fixture_question_mode(self):
        """Test cloze fixture in question mode."""
        html = (FIXTURES_DIR / "cloze.html").read_text()
        result = render_html_to_text(html, mode=RenderMode.QUESTION)
        assert "[...]" in result
        assert "Paris" not in result
        assert "Seine" not in result

    def test_cloze_fixture_answer_mode(self):
        """Test cloze fixture in answer mode."""
        html = (FIXTURES_DIR / "cloze.html").read_text()
        result = render_html_to_text(html, mode=RenderMode.ANSWER)
        assert "Paris" in result
        assert "Seine" in result
        assert "[...]" not in result

    def test_default_mode_is_answer(self):
        """Default render mode should be ANSWER (backward compatible)."""
        html = '<span class="cloze">visible</span>'
        result = render_html_to_text(html)
        assert "visible" in result


class TestStyledSegments:
    """Tests for styled segment rendering."""

    def test_bold_tag_creates_bold_segment(self):
        """Bold tags should create segments with bold style."""
        html = "<b>bold text</b> normal"
        segments = render_html_to_styled_segments(html)
        # Find the bold segment
        bold_segments = [s for s in segments if s.style.bold and "bold" in s.text]
        assert len(bold_segments) >= 1

    def test_italic_tag_creates_italic_segment(self):
        """Italic tags should create segments with italic style."""
        html = "<i>italic text</i>"
        segments = render_html_to_styled_segments(html)
        italic_segments = [s for s in segments if s.style.italic]
        assert len(italic_segments) >= 1

    def test_cloze_answer_mode_creates_cloze_segment(self):
        """Cloze in answer mode should create segment with is_cloze=True."""
        html = '<span class="cloze">answer</span>'
        segments = render_html_to_styled_segments(html, mode=RenderMode.ANSWER)
        cloze_segments = [s for s in segments if s.style.is_cloze]
        assert len(cloze_segments) >= 1
        assert any("answer" in s.text for s in cloze_segments)

    def test_cloze_question_mode_placeholder(self):
        """Cloze in question mode should show [...] placeholder."""
        html = '<span class="cloze">hidden</span>'
        segments = render_html_to_styled_segments(html, mode=RenderMode.QUESTION)
        text = "".join(s.text for s in segments)
        assert "[...]" in text
        assert "hidden" not in text

    def test_inline_style_bold(self):
        """Inline style font-weight:bold should create bold segment."""
        html = '<span style="font-weight: bold;">styled bold</span>'
        segments = render_html_to_styled_segments(html)
        bold_segments = [s for s in segments if s.style.bold]
        assert len(bold_segments) >= 1

    def test_inline_style_color(self):
        """Inline style color should be captured."""
        html = '<span style="color: red;">red text</span>'
        segments = render_html_to_styled_segments(html)
        color_segments = [s for s in segments if s.style.color]
        assert len(color_segments) >= 1
        assert any(s.style.color == "red" for s in color_segments)

    def test_spacing_preserved_around_styled_text(self):
        """Spaces should be preserved around styled segments to prevent word concatenation."""
        html = 'word <b>bold</b> next'
        segments = render_html_to_styled_segments(html)
        text = "".join(s.text for s in segments)
        # Should have spaces between words, not "wordboldnext"
        assert "wordbold" not in text
        assert "boldnext" not in text

    def test_spacing_added_when_missing_around_styled_text(self):
        """Spaces should be added between styled text and adjacent words even if missing in HTML."""
        # HTML without spaces around bold tag
        html = 'word<b>bold</b>next'
        segments = render_html_to_styled_segments(html)
        text = "".join(s.text for s in segments)
        # Should add spaces to prevent "wordboldnext"
        assert "wordbold" not in text
        assert "boldnext" not in text
        assert "word" in text
        assert "bold" in text
        assert "next" in text

    def test_cloze_spacing_preserved(self):
        """Spaces should be preserved around cloze deletions."""
        html = 'The <span class="cloze">answer</span> is here'
        segments = render_html_to_styled_segments(html, mode=RenderMode.ANSWER)
        text = "".join(s.text for s in segments)
        # Should be "The answer is here", not "Theansweris here"
        assert "Theanswer" not in text
        assert "answeris" not in text

    def test_cloze_no_leading_space_at_start(self):
        """Cloze at start of card should not have leading space."""
        html = '<span class="cloze">Answer</span> is the first word'
        segments = render_html_to_styled_segments(html, mode=RenderMode.ANSWER)
        text = "".join(s.text for s in segments)
        # Should not start with a space
        assert not text.startswith(" ")
        assert text.startswith("Answer")

    def test_cloze_spacing_added_when_missing(self):
        """Spaces should be added around cloze even if missing in original HTML."""
        html = 'word<span class="cloze">cloze</span>next'
        segments = render_html_to_styled_segments(html, mode=RenderMode.ANSWER)
        text = "".join(s.text for s in segments)
        # Should add spaces to prevent "wordclozenext"
        assert "wordcloze" not in text
        assert "clozenext" not in text
