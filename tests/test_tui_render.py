"""Tests for tui/render.py - TUI image placeholder parsing and textual-image rendering."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.text import Text

from clanki.render import RenderMode, StyledSegment, TextStyle
from clanki.tui.render import (
    ImagePlaceholder,
    _create_image_renderable,
    _segment_to_rich_style,
    is_image_support_available,
    parse_image_placeholders,
    render_content_with_images,
    render_styled_content_with_images,
    segments_to_rich_text,
)


class TestParseImagePlaceholders:
    """Tests for parse_image_placeholders function."""

    def test_empty_string(self):
        """Empty string should return empty list."""
        result = parse_image_placeholders("")
        assert result == []

    def test_no_placeholders(self):
        """Text without placeholders should return empty list."""
        result = parse_image_placeholders("Hello world, no images here.")
        assert result == []

    def test_single_placeholder(self):
        """Single placeholder should be found."""
        result = parse_image_placeholders("Here is [image: photo.jpg] the image.")
        assert len(result) == 1
        assert result[0].filename == "photo.jpg"
        assert result[0].start == 8
        assert result[0].end == 26  # "[image: photo.jpg]" is 18 chars, 8 + 18 = 26

    def test_multiple_placeholders(self):
        """Multiple placeholders should all be found."""
        text = "[image: first.png] text [image: second.jpg]"
        result = parse_image_placeholders(text)
        assert len(result) == 2
        assert result[0].filename == "first.png"
        assert result[1].filename == "second.jpg"

    def test_placeholder_with_spaces(self):
        """Placeholder with extra spaces should be parsed."""
        result = parse_image_placeholders("[image:   spacy.png  ]")
        assert len(result) == 1
        assert result[0].filename == "spacy.png"

    def test_placeholder_with_path(self):
        """Placeholder with path should preserve the path."""
        result = parse_image_placeholders("[image: path/to/image.png]")
        assert len(result) == 1
        assert result[0].filename == "path/to/image.png"

    def test_placeholder_with_special_chars(self):
        """Placeholder with special characters should work."""
        result = parse_image_placeholders("[image: image-name_123.png]")
        assert len(result) == 1
        assert result[0].filename == "image-name_123.png"

    def test_placeholder_unicode_filename(self):
        """Placeholder with unicode filename should work."""
        result = parse_image_placeholders("[image: 画像.png]")
        assert len(result) == 1
        assert result[0].filename == "画像.png"

    def test_positions_are_correct(self):
        """Placeholder positions should match the text."""
        text = "before [image: test.jpg] after"
        result = parse_image_placeholders(text)
        assert len(result) == 1
        # Verify the positions by slicing
        assert text[result[0].start : result[0].end] == "[image: test.jpg]"


class TestImageSupportAvailability:
    """Tests for image support availability checking."""

    def test_is_image_support_available_returns_true(self):
        """is_image_support_available should always return True since textual-image is a dependency."""
        result = is_image_support_available()
        assert result is True


class TestCreateImageRenderable:
    """Tests for _create_image_renderable function."""

    def test_returns_none_if_file_missing(self):
        """Should return None if image file doesn't exist."""
        result = _create_image_renderable(Path("/nonexistent/image.png"))
        assert result is None

    def test_creates_image_when_file_exists(self, tmp_path):
        """Should create an Image renderable when file exists."""
        # Create a minimal valid image file (1x1 PNG)
        image_path = tmp_path / "test.png"
        # Write a minimal valid 1x1 PNG file
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        image_path.write_bytes(png_data)

        with patch("clanki.tui.render.Image") as mock_image:
            mock_instance = MagicMock()
            mock_image.return_value = mock_instance
            result = _create_image_renderable(image_path, max_width=40, max_height=20)

            mock_image.assert_called_once_with(image_path, width=40, height=20)
            assert result == mock_instance

    def test_returns_none_on_exception(self, tmp_path):
        """Should return None if Image creation raises an exception."""
        image_path = tmp_path / "test.png"
        image_path.touch()

        with patch("clanki.tui.render.Image", side_effect=Exception("Test error")):
            result = _create_image_renderable(image_path)
            assert result is None


class TestRenderContentWithImages:
    """Tests for render_content_with_images function."""

    def test_empty_text(self):
        """Empty text should return empty list."""
        result = render_content_with_images("", None, True)
        assert result == []

    def test_text_without_placeholders(self):
        """Text without placeholders should return single Text item."""
        result = render_content_with_images("Hello world", None, True)
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert str(result[0]) == "Hello world"

    def test_images_disabled_returns_text(self):
        """With images disabled, should return original text."""
        text = "Before [image: test.jpg] after"
        result = render_content_with_images(text, None, images_enabled=False)
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert str(result[0]) == text

    def test_no_media_dir_keeps_placeholder(self):
        """Without media dir, should keep placeholder text."""
        text = "Before [image: test.jpg] after"
        result = render_content_with_images(text, None, images_enabled=True)
        # Without media_dir, should produce 3 items: text before, placeholder, text after
        assert len(result) == 3
        assert isinstance(result[0], Text)
        assert isinstance(result[1], Text)
        assert isinstance(result[2], Text)
        # First should be "Before "
        assert str(result[0]) == "Before "
        # Second should be the placeholder
        assert str(result[1]) == "[image: test.jpg]"
        # Third should be " after"
        assert str(result[2]) == " after"

    def test_missing_file_keeps_placeholder(self, tmp_path):
        """Missing image file should keep placeholder text."""
        text = "[image: nonexistent.jpg]"
        result = render_content_with_images(text, tmp_path, images_enabled=True)
        # Should return exactly one item: the placeholder text
        assert len(result) == 1
        assert isinstance(result[0], Text)
        # Placeholder should be exactly preserved
        assert str(result[0]) == "[image: nonexistent.jpg]"

    def test_existing_file_creates_image_renderable(self, tmp_path):
        """Existing image file should create Image renderable."""
        # Create a test image file
        image_path = tmp_path / "test.jpg"
        image_path.touch()

        text = "[image: test.jpg]"
        with patch("clanki.tui.render._create_image_renderable") as mock_create:
            mock_image = MagicMock()
            mock_create.return_value = mock_image
            result = render_content_with_images(text, tmp_path, images_enabled=True)

            assert len(result) == 1
            assert result[0] == mock_image

    def test_preserves_text_before_placeholder(self, tmp_path):
        """Text before placeholder should be preserved."""
        text = "Before text [image: test.jpg]"
        result = render_content_with_images(text, tmp_path, images_enabled=True)
        # Should have 2 items: text before and the placeholder
        assert len(result) == 2
        assert isinstance(result[0], Text)
        assert isinstance(result[1], Text)
        # First item should be exactly "Before text "
        assert str(result[0]) == "Before text "
        # Second item should be the placeholder
        assert str(result[1]) == "[image: test.jpg]"

    def test_preserves_text_after_placeholder(self, tmp_path):
        """Text after placeholder should be preserved."""
        text = "[image: test.jpg] After text"
        result = render_content_with_images(text, tmp_path, images_enabled=True)
        # Should have 2 items: placeholder and text after
        assert len(result) == 2
        assert isinstance(result[0], Text)
        assert isinstance(result[1], Text)
        # First item should be the placeholder
        assert str(result[0]) == "[image: test.jpg]"
        # Second item should be exactly " After text"
        assert str(result[1]) == " After text"

    def test_multiple_placeholders(self, tmp_path):
        """Multiple placeholders should all be handled."""
        text = "One [image: a.jpg] two [image: b.jpg] three"
        result = render_content_with_images(text, tmp_path, images_enabled=True)
        # Should have 5 items: text, placeholder, text, placeholder, text
        assert len(result) == 5
        # Verify each item type and content
        assert isinstance(result[0], Text)
        assert str(result[0]) == "One "
        assert isinstance(result[1], Text)
        assert str(result[1]) == "[image: a.jpg]"
        assert isinstance(result[2], Text)
        assert str(result[2]) == " two "
        assert isinstance(result[3], Text)
        assert str(result[3]) == "[image: b.jpg]"
        assert isinstance(result[4], Text)
        assert str(result[4]) == " three"


class TestImagePlaceholderDataclass:
    """Tests for ImagePlaceholder dataclass."""

    def test_creation(self):
        """ImagePlaceholder should store all fields."""
        placeholder = ImagePlaceholder(filename="test.jpg", start=10, end=25)
        assert placeholder.filename == "test.jpg"
        assert placeholder.start == 10
        assert placeholder.end == 25

    def test_equality(self):
        """Two placeholders with same values should be equal."""
        p1 = ImagePlaceholder(filename="test.jpg", start=10, end=25)
        p2 = ImagePlaceholder(filename="test.jpg", start=10, end=25)
        assert p1 == p2

    def test_inequality(self):
        """Placeholders with different values should not be equal."""
        p1 = ImagePlaceholder(filename="test.jpg", start=10, end=25)
        p2 = ImagePlaceholder(filename="other.jpg", start=10, end=25)
        assert p1 != p2


class TestSegmentToRichStyle:
    """Tests for _segment_to_rich_style function."""

    def test_default_style_returns_empty(self):
        """Default style should return empty Rich Style."""
        segment = StyledSegment(text="test", style=TextStyle())
        style = _segment_to_rich_style(segment)
        # Empty style has no attributes set
        assert style.bold is None or style.bold is False

    def test_bold_style(self):
        """Bold style should set bold attribute."""
        segment = StyledSegment(text="test", style=TextStyle(bold=True))
        style = _segment_to_rich_style(segment)
        assert style.bold is True

    def test_italic_style(self):
        """Italic style should set italic attribute."""
        segment = StyledSegment(text="test", style=TextStyle(italic=True))
        style = _segment_to_rich_style(segment)
        assert style.italic is True

    def test_underline_style(self):
        """Underline style should set underline attribute."""
        segment = StyledSegment(text="test", style=TextStyle(underline=True))
        style = _segment_to_rich_style(segment)
        assert style.underline is True

    def test_strikethrough_style(self):
        """Strikethrough style should set strike attribute."""
        segment = StyledSegment(text="test", style=TextStyle(strikethrough=True))
        style = _segment_to_rich_style(segment)
        assert style.strike is True

    def test_cloze_style_sets_bold_and_reverse(self):
        """Cloze style should set bold and reverse for visibility."""
        segment = StyledSegment(text="test", style=TextStyle(is_cloze=True))
        style = _segment_to_rich_style(segment)
        assert style.bold is True
        assert style.reverse is True


class TestSegmentsToRichText:
    """Tests for segments_to_rich_text function."""

    def test_empty_segments(self):
        """Empty segments should return empty Text."""
        text = segments_to_rich_text([])
        assert str(text) == ""

    def test_single_segment(self):
        """Single segment should be converted to Text."""
        segments = [StyledSegment(text="hello", style=TextStyle())]
        text = segments_to_rich_text(segments)
        assert str(text) == "hello"

    def test_multiple_segments(self):
        """Multiple segments should be concatenated."""
        segments = [
            StyledSegment(text="hello ", style=TextStyle()),
            StyledSegment(text="world", style=TextStyle(bold=True)),
        ]
        text = segments_to_rich_text(segments)
        assert str(text) == "hello world"


class TestRenderStyledContentWithImages:
    """Tests for render_styled_content_with_images function."""

    def test_empty_html(self):
        """Empty HTML should return empty list."""
        result = render_styled_content_with_images("", None, True)
        assert result == []

    def test_simple_html(self):
        """Simple HTML should be rendered to styled text."""
        result = render_styled_content_with_images(
            "<div>Hello world</div>", None, True
        )
        assert len(result) >= 1
        assert isinstance(result[0], Text)
        assert "Hello world" in str(result[0])

    def test_cloze_question_mode(self):
        """Cloze in question mode should show placeholder."""
        html = '<span class="cloze">answer</span>'
        result = render_styled_content_with_images(
            html, None, True, mode=RenderMode.QUESTION
        )
        assert len(result) >= 1
        text = str(result[0])
        assert "[...]" in text
        assert "answer" not in text

    def test_cloze_answer_mode(self):
        """Cloze in answer mode should show styled answer."""
        html = '<span class="cloze">answer</span>'
        result = render_styled_content_with_images(
            html, None, True, mode=RenderMode.ANSWER
        )
        assert len(result) >= 1
        text = str(result[0])
        assert "answer" in text
        assert "[...]" not in text

    def test_bold_text_styled(self):
        """Bold HTML should create styled Rich Text."""
        html = "<b>bold</b> normal"
        result = render_styled_content_with_images(html, None, True)
        assert len(result) >= 1
        # The result should be a Rich Text object with styling
        assert isinstance(result[0], Text)
