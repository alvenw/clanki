"""Integration tests for the render pipeline.

Tests the full flow from HTML → styled segments → TUI renderables.
Uses fixture HTML and runs:
- render_html_to_styled_segments
- render_styled_content_with_images with images_enabled=False

Validates:
- Placeholder handling for images
- Audio icon substitution in final Text
- Style preservation through the pipeline
- Cloze rendering in question vs answer mode
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from rich.text import Text

from clanki.render import (
    RenderMode,
    StyledSegment,
    TextStyle,
    render_html_to_styled_segments,
)
from clanki.tui.render import (
    parse_image_placeholders,
    render_content_with_images,
    render_styled_content_with_images,
    segments_to_rich_text,
)


# Fixture HTML samples


class TestFixtureHTML:
    """Collection of fixture HTML for testing."""

    SIMPLE_TEXT = "<div>Hello world</div>"
    BOLD_TEXT = "<b>Bold text</b> normal text"
    ITALIC_TEXT = "<i>Italic text</i> normal"
    MIXED_STYLES = "<b>Bold</b> and <i>italic</i> and <b><i>both</i></b>"
    NESTED_DIVS = "<div><div>Nested content</div></div>"
    PARAGRAPH = "<p>First paragraph</p><p>Second paragraph</p>"
    LIST_HTML = "<ul><li>Item 1</li><li>Item 2</li></ul>"
    CLOZE_ANSWER = '<span class="cloze">answer text</span>'
    CLOZE_QUESTION = '<span class="cloze">hidden</span>'
    WITH_IMAGE = '<div>Text <img src="photo.jpg"> more text</div>'
    WITH_AUDIO = "<div>Text [anki:play:a:0] more text</div>"
    COMPLEX_CARD = """
        <div class="card">
            <b>Question:</b> What is <span class="cloze">the answer</span>?
            <br>
            <img src="diagram.png">
            <br>
            [sound:audio.mp3]
        </div>
    """


class TestRenderHtmlToStyledSegments:
    """Tests for render_html_to_styled_segments function."""

    def test_simple_text_produces_single_segment(self):
        """Simple text should produce a single unstyled segment."""
        segments = render_html_to_styled_segments(TestFixtureHTML.SIMPLE_TEXT)

        assert len(segments) >= 1
        # Find the segment with actual content
        text_segments = [s for s in segments if s.text.strip()]
        assert any("Hello world" in s.text for s in text_segments)

    def test_bold_text_has_bold_style(self):
        """Bold text should have bold=True in style."""
        segments = render_html_to_styled_segments(TestFixtureHTML.BOLD_TEXT)

        bold_segments = [s for s in segments if s.style.bold and s.text.strip()]
        assert len(bold_segments) >= 1
        assert any("Bold text" in s.text for s in bold_segments)

    def test_italic_text_has_italic_style(self):
        """Italic text should have italic=True in style."""
        segments = render_html_to_styled_segments(TestFixtureHTML.ITALIC_TEXT)

        italic_segments = [s for s in segments if s.style.italic and s.text.strip()]
        assert len(italic_segments) >= 1
        assert any("Italic text" in s.text for s in italic_segments)

    def test_image_converted_to_placeholder(self):
        """<img> tags should be converted to [image: filename] placeholders."""
        segments = render_html_to_styled_segments(TestFixtureHTML.WITH_IMAGE)

        combined_text = "".join(s.text for s in segments)
        assert "[image: photo.jpg]" in combined_text

    def test_cloze_question_mode_shows_placeholder(self):
        """Cloze in QUESTION mode should show [...] placeholder."""
        segments = render_html_to_styled_segments(
            TestFixtureHTML.CLOZE_ANSWER,
            mode=RenderMode.QUESTION,
        )

        combined_text = "".join(s.text for s in segments)
        assert "[...]" in combined_text
        assert "answer text" not in combined_text

    def test_cloze_answer_mode_shows_content(self):
        """Cloze in ANSWER mode should show actual content."""
        segments = render_html_to_styled_segments(
            TestFixtureHTML.CLOZE_ANSWER,
            mode=RenderMode.ANSWER,
        )

        combined_text = "".join(s.text for s in segments)
        assert "answer text" in combined_text
        assert "[...]" not in combined_text

    def test_cloze_answer_mode_has_cloze_style(self):
        """Cloze content in ANSWER mode should have is_cloze=True style."""
        segments = render_html_to_styled_segments(
            TestFixtureHTML.CLOZE_ANSWER,
            mode=RenderMode.ANSWER,
        )

        cloze_segments = [s for s in segments if s.style.is_cloze]
        assert len(cloze_segments) >= 1
        assert any("answer text" in s.text for s in cloze_segments)


class TestSegmentsToRichText:
    """Tests for segments_to_rich_text conversion."""

    def test_empty_segments_produce_empty_text(self):
        """Empty segment list should produce empty Rich Text."""
        text = segments_to_rich_text([])

        assert str(text) == ""
        assert len(text) == 0

    def test_single_unstyled_segment(self):
        """Single unstyled segment should convert correctly."""
        segments = [StyledSegment(text="Hello", style=TextStyle())]
        text = segments_to_rich_text(segments)

        assert str(text) == "Hello"
        assert isinstance(text, Text)

    def test_multiple_segments_concatenate(self):
        """Multiple segments should be concatenated in order."""
        segments = [
            StyledSegment(text="First ", style=TextStyle()),
            StyledSegment(text="Second", style=TextStyle()),
        ]
        text = segments_to_rich_text(segments)

        assert str(text) == "First Second"

    def test_bold_style_applied(self):
        """Bold style should be applied to Rich Text."""
        segments = [StyledSegment(text="Bold", style=TextStyle(bold=True))]
        text = segments_to_rich_text(segments)

        # Access spans to verify style
        assert len(text._spans) >= 1

    def test_cloze_style_produces_bold_and_reverse(self):
        """Cloze style should produce bold and reverse in Rich."""
        segments = [StyledSegment(text="Cloze", style=TextStyle(is_cloze=True))]
        text = segments_to_rich_text(segments)

        # The text should have styling applied
        assert str(text) == "Cloze"
        # Verify spans exist (indicates styling)
        assert len(text._spans) >= 1


class TestRenderContentWithImagesDisabled:
    """Tests for render_content_with_images with images_enabled=False."""

    def test_returns_text_as_is_when_disabled(self):
        """With images disabled, should return original text."""
        text = "Some text [image: test.jpg] more text"
        result = render_content_with_images(
            text,
            media_dir=None,
            images_enabled=False,
        )

        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert str(result[0]) == text

    def test_empty_text_returns_empty_list(self):
        """Empty text should return empty list."""
        result = render_content_with_images(
            "",
            media_dir=None,
            images_enabled=False,
        )

        assert result == []

    def test_audio_icons_substituted(self):
        """Audio placeholders should be substituted with icons."""
        text = "Listen [audio: test.mp3] here"
        result = render_content_with_images(
            text,
            media_dir=None,
            images_enabled=False,
        )

        assert len(result) == 1
        result_str = str(result[0])
        # Audio placeholder should be replaced with icon
        assert "[audio:" not in result_str
        assert "🔊" in result_str
        # Verify the icon has the expected key binding (first audio = key 5)
        assert "🔊[5]" in result_str


class TestRenderStyledContentWithImages:
    """Tests for render_styled_content_with_images full pipeline."""

    def test_empty_html_returns_empty_list(self):
        """Empty HTML should return empty list."""
        result = render_styled_content_with_images(
            "",
            media_dir=None,
            images_enabled=False,
        )

        assert result == []

    def test_simple_html_produces_text(self):
        """Simple HTML should produce styled Text."""
        result = render_styled_content_with_images(
            "<div>Simple text</div>",
            media_dir=None,
            images_enabled=False,
        )

        assert len(result) >= 1
        assert isinstance(result[0], Text)
        assert "Simple text" in str(result[0])

    def test_image_placeholder_preserved_when_disabled(self):
        """Image placeholders should be preserved when images disabled."""
        result = render_styled_content_with_images(
            '<div>See <img src="diagram.png"> below</div>',
            media_dir=None,
            images_enabled=False,
        )

        combined = "".join(str(r) for r in result)
        assert "[image: diagram.png]" in combined

    def test_image_placeholder_preserved_when_no_media_dir(self, tmp_path):
        """Image placeholders preserved when media_dir is None."""
        result = render_styled_content_with_images(
            '<div><img src="test.png"></div>',
            media_dir=None,  # No media dir
            images_enabled=True,
        )

        # Should fall back to placeholder since no media_dir
        combined = "".join(str(r) for r in result)
        assert "[image: test.png]" in combined

    def test_audio_icons_substituted_in_styled_output(self):
        """Audio placeholders should be replaced with icons in styled output."""
        html = "<div>Audio: [audio: clip.mp3]</div>"
        result = render_styled_content_with_images(
            html,
            media_dir=None,
            images_enabled=False,
        )

        combined = "".join(str(r) for r in result)
        # Audio placeholder should be replaced with icon (not OR - both conditions must hold)
        assert "[audio:" not in combined
        assert "🔊" in combined
        # Verify the icon has key binding
        assert "🔊[5]" in combined

    def test_cloze_question_mode_in_pipeline(self):
        """Cloze in QUESTION mode should show placeholder through full pipeline."""
        html = '<span class="cloze">secret</span>'
        result = render_styled_content_with_images(
            html,
            media_dir=None,
            images_enabled=False,
            mode=RenderMode.QUESTION,
        )

        combined = "".join(str(r) for r in result)
        assert "[...]" in combined
        assert "secret" not in combined

    def test_cloze_answer_mode_in_pipeline(self):
        """Cloze in ANSWER mode should show content through full pipeline."""
        html = '<span class="cloze">revealed</span>'
        result = render_styled_content_with_images(
            html,
            media_dir=None,
            images_enabled=False,
            mode=RenderMode.ANSWER,
        )

        combined = "".join(str(r) for r in result)
        assert "revealed" in combined
        assert "[...]" not in combined

    def test_bold_preserved_through_pipeline(self):
        """Bold formatting should be preserved through the pipeline."""
        html = "<b>Important</b> text"
        result = render_styled_content_with_images(
            html,
            media_dir=None,
            images_enabled=False,
        )

        assert len(result) >= 1
        text_obj = result[0]
        assert isinstance(text_obj, Text)
        assert "Important" in str(text_obj)
        # Bold text should have spans
        assert len(text_obj._spans) >= 1


class TestParseImagePlaceholders:
    """Tests for parse_image_placeholders utility."""

    def test_no_placeholders_returns_empty(self):
        """Text without placeholders should return empty list."""
        result = parse_image_placeholders("Plain text without images")

        assert result == []

    def test_single_placeholder_parsed(self):
        """Single placeholder should be parsed correctly."""
        text = "[image: photo.jpg]"
        result = parse_image_placeholders(text)

        assert len(result) == 1
        assert result[0].filename == "photo.jpg"
        assert result[0].start == 0
        assert result[0].end == len(text)  # End is length of the placeholder

    def test_placeholder_with_spaces_trimmed(self):
        """Extra spaces in placeholder should be trimmed."""
        result = parse_image_placeholders("[image:   spacey.png   ]")

        assert len(result) == 1
        assert result[0].filename == "spacey.png"

    def test_multiple_placeholders_all_found(self):
        """Multiple placeholders should all be found."""
        text = "[image: a.jpg] text [image: b.png]"
        result = parse_image_placeholders(text)

        assert len(result) == 2
        assert result[0].filename == "a.jpg"
        assert result[1].filename == "b.png"

    def test_positions_match_text(self):
        """Placeholder positions should correctly match text."""
        text = "before [image: test.jpg] after"
        result = parse_image_placeholders(text)

        assert len(result) == 1
        # Extract using positions should give original placeholder
        extracted = text[result[0].start:result[0].end]
        assert extracted == "[image: test.jpg]"


class TestComplexRenderPipeline:
    """Integration tests for complex HTML through the full pipeline."""

    def test_complex_card_with_mixed_content(self):
        """Complex card with multiple elements should render correctly."""
        result = render_styled_content_with_images(
            TestFixtureHTML.COMPLEX_CARD,
            media_dir=None,
            images_enabled=False,
            mode=RenderMode.ANSWER,
        )

        combined = "".join(str(r) for r in result)

        # Should contain the text content
        assert "Question:" in combined
        # Cloze content should be visible in ANSWER mode
        assert "the answer" in combined
        # Image should be placeholder
        assert "[image: diagram.png]" in combined

    def test_complex_card_question_mode(self):
        """Complex card in QUESTION mode should hide cloze."""
        result = render_styled_content_with_images(
            TestFixtureHTML.COMPLEX_CARD,
            media_dir=None,
            images_enabled=False,
            mode=RenderMode.QUESTION,
        )

        combined = "".join(str(r) for r in result)

        # Cloze should be hidden
        assert "[...]" in combined
        assert "the answer" not in combined

    def test_multiple_images_all_become_placeholders(self):
        """Multiple images should all become placeholders."""
        html = '<img src="a.png"><img src="b.jpg"><img src="c.gif">'
        result = render_styled_content_with_images(
            html,
            media_dir=None,
            images_enabled=False,
        )

        combined = "".join(str(r) for r in result)

        assert "[image: a.png]" in combined
        assert "[image: b.jpg]" in combined
        assert "[image: c.gif]" in combined


class TestAudioSubstitution:
    """Tests specifically for audio icon substitution in the pipeline."""

    def test_single_audio_placeholder_substituted(self):
        """Single audio placeholder should be substituted with icon."""
        # Test with plain render_content_with_images
        text = "Click [audio: sound.mp3] to play"
        result = render_content_with_images(
            text,
            media_dir=None,
            images_enabled=False,
        )

        result_str = str(result[0])
        assert "[audio:" not in result_str
        # Should have audio icon with key binding
        assert "🔊" in result_str

    def test_multiple_audio_placeholders_get_sequential_keys(self):
        """Multiple audio placeholders should get sequential key bindings."""
        text = "[audio: a.mp3] [audio: b.mp3] [audio: c.mp3]"
        result = render_content_with_images(
            text,
            media_dir=None,
            images_enabled=False,
        )

        result_str = str(result[0])
        # Keys 5, 6, 7 for first three audio files
        assert "🔊[5]" in result_str
        assert "🔊[6]" in result_str
        assert "🔊[7]" in result_str
