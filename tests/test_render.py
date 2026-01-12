"""Tests for render/html.py - HTML to terminal text conversion."""

from pathlib import Path

from clanki.render.html import render_html_to_text

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
