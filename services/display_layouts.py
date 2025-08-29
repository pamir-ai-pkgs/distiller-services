"""
Component-based layout system for e-ink display.

Provides high-level components that automatically handle positioning,
spacing, and rendering without manual coordinate calculations.
"""

from abc import ABC, abstractmethod

import qrcode
from PIL import Image, ImageDraw, ImageFont

from .display_theme import theme


class Component(ABC):
    """Base class for all display components."""

    @abstractmethod
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """
        Render the component and return the height consumed.

        Args:
            draw: PIL ImageDraw object
            x: Starting x position
            y: Starting y position
            width: Available width
            fonts: Dictionary of loaded fonts

        Returns:
            Height consumed by this component
        """
        pass


class Text(Component):
    """Text component with automatic wrapping and styling."""

    def __init__(self, text: str, style: str = "body", align: str = "left"):
        """
        Create a text component.

        Args:
            text: Text to display
            style: Style name from theme (title, subtitle, body, label, value, caption)
            align: Text alignment (left, center, right)
        """
        self.text = text
        self.style = style
        self.align = align

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """Render text with automatic wrapping."""
        if not self.text:
            return 0

        style_config = theme.get_text_style(self.style)
        font = fonts.get(style_config["font"], fonts.get("small"))

        # Apply uppercase if specified
        display_text = self.text.upper() if style_config.get("uppercase", False) else self.text

        # Wrap text to fit width
        lines = self._wrap_text(display_text, font, width)

        # Calculate line height
        line_height = font.size + theme.spacing.between_lines
        total_height = 0

        # Render each line
        for line in lines:
            # Calculate x position based on alignment
            if self.align == "center":
                bbox = font.getbbox(line)
                text_width = bbox[2] - bbox[0]
                line_x = x + (width - text_width) // 2
            elif self.align == "right":
                bbox = font.getbbox(line)
                text_width = bbox[2] - bbox[0]
                line_x = x + width - text_width
            else:  # left
                line_x = x

            draw.text((line_x, y + total_height), line, font=font, fill=theme.colors.foreground)
            total_height += line_height

        return total_height

    def _wrap_text(self, text: str, font: ImageFont, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = font.getbbox(test_line)
            if bbox[2] - bbox[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

                # Check if single word is too long
                if font.getbbox(word)[2] - font.getbbox(word)[0] > max_width:
                    # Break long word
                    while len(word) > 0:
                        for i in range(len(word), 0, -1):
                            if font.getbbox(word[:i])[2] - font.getbbox(word[:i])[0] <= max_width:
                                lines.append(word[:i])
                                word = word[i:]
                                break
                        else:
                            # Word is too long even for one character, force break
                            lines.append(word[0])
                            word = word[1:]
                    current_line = []

        if current_line:
            lines.append(" ".join(current_line))

        return lines if lines else [""]


class Title(Text):
    """Title component - just Text with title style preset."""

    def __init__(self, text: str, align: str = "center"):
        super().__init__(text, style="title", align=align)


class Subtitle(Text):
    """Subtitle component - Text with subtitle style preset."""

    def __init__(self, text: str, align: str = "center"):
        super().__init__(text, style="subtitle", align=align)


class Label(Text):
    """Label component - Text with label style preset."""

    def __init__(self, text: str, align: str = "left"):
        super().__init__(text, style="label", align=align)


class Value(Text):
    """Value component - Text with value style preset."""

    def __init__(self, text: str, align: str = "left"):
        super().__init__(text, style="value", align=align)


class Caption(Text):
    """Caption component - Text with caption style preset."""

    def __init__(self, text: str, align: str = "center"):
        super().__init__(text, style="caption", align=align)


class Space(Component):
    """Empty space component for layout control."""

    def __init__(self, height: int | None = None):
        """
        Create a space component.

        Args:
            height: Fixed height in pixels, or None for default spacing
        """
        self.height = height or theme.spacing.between_components

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """Return the height without drawing anything."""
        return self.height


class QRCode(Component):
    """QR Code component."""

    def __init__(self, data: str, size: str = "medium", align: str = "center"):
        """
        Create a QR code component.

        Args:
            data: Data to encode in QR code
            size: Size preset (small, medium, large)
            align: Horizontal alignment (left, center, right)
        """
        self.data = data
        self.size = theme.get_qr_size(size)
        self.align = align

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """Render QR code."""
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=3,
            border=1,
        )
        qr.add_data(self.data)
        qr.make(fit=True)

        # Create QR image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((self.size, self.size), Image.NEAREST)

        # Calculate position based on alignment
        if self.align == "center":
            qr_x = x + (width - self.size) // 2
        elif self.align == "right":
            qr_x = x + width - self.size
        else:  # left
            qr_x = x

        # Draw QR code by copying pixels
        # Convert QR to monochrome if needed
        if qr_img.mode != "1":
            qr_img = qr_img.convert("1")

        # Draw each pixel of the QR code
        pixels = qr_img.load()
        for dy in range(self.size):
            for dx in range(self.size):
                if pixels[dx, dy] == 0:  # Black pixel in QR
                    draw.point((qr_x + dx, y + dy), fill=theme.colors.foreground)

        return self.size


class ProgressBar(Component):
    """Progress bar component."""

    def __init__(self, progress: float, show_percentage: bool = True):
        """
        Create a progress bar.

        Args:
            progress: Progress value (0.0 to 1.0)
            show_percentage: Whether to show percentage text below
        """
        self.progress = max(0.0, min(1.0, progress))
        self.show_percentage = show_percentage

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """Render progress bar."""
        bar_width = min(width, theme.components.progress_bar_width)
        bar_height = theme.components.progress_bar_height

        # Center the bar
        bar_x = x + (width - bar_width) // 2

        # Draw outer rectangle
        draw.rectangle(
            [(bar_x, y), (bar_x + bar_width, y + bar_height)],
            outline=theme.colors.foreground,
            width=theme.components.progress_bar_border,
        )

        # Draw fill
        if self.progress > 0:
            fill_width = int((bar_width - 4) * self.progress)
            if fill_width > 0:
                draw.rectangle(
                    [(bar_x + 2, y + 2), (bar_x + 2 + fill_width, y + bar_height - 2)],
                    fill=theme.colors.foreground,
                )

        total_height = bar_height

        # Draw percentage if requested
        if self.show_percentage:
            percentage_text = f"{int(self.progress * 100)}%"
            font = fonts.get("small")
            bbox = font.getbbox(percentage_text)
            text_width = bbox[2] - bbox[0]
            text_x = x + (width - text_width) // 2
            draw.text(
                (text_x, y + bar_height + theme.spacing.xs),
                percentage_text,
                font=font,
                fill=theme.colors.foreground,
            )
            total_height += font.size + theme.spacing.xs

        return total_height


class Checkmark(Component):
    """Checkmark icon component."""

    def __init__(self, size: str = "medium", align: str = "center"):
        """
        Create a checkmark component.

        Args:
            size: Size preset (small, medium, large)
            align: Horizontal alignment
        """
        sizes = {"small": 16, "medium": 24, "large": 32}
        self.size = sizes.get(size, 24)
        self.align = align

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """Render checkmark."""
        # Calculate position
        if self.align == "center":
            check_x = x + (width - self.size) // 2
        elif self.align == "right":
            check_x = x + width - self.size
        else:
            check_x = x

        # Draw checkmark
        cx = check_x + self.size // 2
        cy = y + self.size // 2

        # Draw checkmark lines
        draw.line(
            [(cx - self.size // 3, cy), (cx - self.size // 6, cy + self.size // 3)],
            fill=theme.colors.foreground,
            width=theme.components.checkmark_stroke,
        )
        draw.line(
            [
                (cx - self.size // 6, cy + self.size // 3),
                (cx + self.size // 3, cy - self.size // 3),
            ],
            fill=theme.colors.foreground,
            width=theme.components.checkmark_stroke,
        )

        return self.size


class Dots(Component):
    """Animated dots component (for loading states)."""

    def __init__(self, count: int = 3, align: str = "center"):
        """
        Create a dots component.

        Args:
            count: Number of dots
            align: Horizontal alignment
        """
        self.count = count
        self.align = align

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """Render dots."""
        dots_text = " • " * self.count
        font = fonts.get("large")

        bbox = font.getbbox(dots_text)
        text_width = bbox[2] - bbox[0]

        if self.align == "center":
            dots_x = x + (width - text_width) // 2
        elif self.align == "right":
            dots_x = x + width - text_width
        else:
            dots_x = x

        draw.text((dots_x, y), dots_text, font=font, fill=theme.colors.foreground)

        return font.size


class Checklist(Component):
    """Checklist component for status items."""

    def __init__(self, items: list[tuple[str, bool]], spacing: int = 4):
        """
        Create a checklist.

        Args:
            items: List of (text, checked) tuples
        """
        self.items = items
        self.spacing = spacing

    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, fonts: dict) -> int:
        """Render checklist."""
        font = fonts.get("small")
        line_height = font.size + self.spacing
        total_height = 0

        for text, checked in self.items:
            # Draw checkbox or checkmark
            mark = "" if checked else ""
            draw.text((x, y + total_height), mark, font=font, fill=theme.colors.foreground)

            # Draw text
            text_x = x + 16  # Space for mark
            draw.text((text_x, y + total_height), text, font=font, fill=theme.colors.foreground)

            total_height += line_height

        return total_height


class Layout:
    """Main layout manager for composing screens."""

    def __init__(self, width: int | None = None, height: int | None = None):
        """
        Create a layout manager.

        Args:
            width: Layout width (defaults to theme content width)
            height: Layout height (defaults to theme content height)
        """
        self.width = width or theme.layout.content_width
        self.height = height or theme.layout.content_height
        self.components: list[Component] = []

    def add(self, *components: Component) -> "Layout":
        """
        Add components to the layout.

        Args:
            components: Components to add

        Returns:
            Self for chaining
        """
        for component in components:
            if component is not None:
                self.components.append(component)
        return self

    def render(self, fonts: dict) -> Image.Image:
        """
        Render all components to an image.

        Args:
            fonts: Dictionary of loaded fonts

        Returns:
            PIL Image with rendered components
        """
        # Create image
        image = Image.new("1", (theme.display.width, theme.display.height), theme.colors.background)
        draw = ImageDraw.Draw(image)
        draw.fontmode = "L"

        # Start from safe area
        x = theme.spacing.margin
        y = theme.spacing.margin

        # Render each component
        for i, component in enumerate(self.components):
            # Add spacing between components (except first)
            if i > 0 and not isinstance(component, Space):
                # Don't add spacing if previous was Space
                if not isinstance(self.components[i - 1], Space):
                    y += theme.spacing.between_components

            # Render component
            height = component.render(draw, x, y, self.width, fonts)
            y += height

            # Stop if we exceed display height
            if y > theme.display.height - theme.spacing.margin:
                break

        return image

    def clear(self) -> "Layout":
        """Clear all components."""
        self.components = []
        return self


class LandscapeLayout:
    """Layout manager for two-column landscape-oriented layouts."""

    def __init__(self):
        """Create a landscape layout with left and right columns."""
        self.left_components: list[Component] = []
        self.right_components: list[Component] = []
        self.left_width = theme.layout.left_column_width
        self.right_width = theme.layout.right_column_width
        self.column_gap = theme.layout.column_gap

    def add_left(self, *components: Component) -> "LandscapeLayout":
        """
        Add components to the left column.

        Args:
            components: Components to add to left column

        Returns:
            Self for chaining
        """
        for component in components:
            if component is not None:
                self.left_components.append(component)
        return self

    def add_right(self, *components: Component) -> "LandscapeLayout":
        """
        Add components to the right column.

        Args:
            components: Components to add to right column

        Returns:
            Self for chaining
        """
        for component in components:
            if component is not None:
                self.right_components.append(component)
        return self

    def render(self, fonts: dict) -> Image.Image:
        """
        Render the two-column layout to an image.

        Args:
            fonts: Dictionary of loaded fonts

        Returns:
            PIL Image with rendered components
        """
        # Landscape canvas
        landscape_width = 250
        landscape_height = 128
        image = Image.new("1", (landscape_width, landscape_height), theme.colors.background)
        draw = ImageDraw.Draw(image)
        draw.fontmode = "L"

        margin = 10
        left_column_width = 100
        right_column_width = 120
        column_gap = 10

        left_x = margin
        right_x = margin + left_column_width + column_gap
        start_y = margin

        # Render left column
        y = start_y
        for i, component in enumerate(self.left_components):
            # Add spacing between components (except first)
            if i > 0 and not isinstance(component, Space):
                if not isinstance(self.left_components[i - 1], Space):
                    y += theme.spacing.between_components

            # Render component
            height = component.render(draw, left_x, y, left_column_width, fonts)
            y += height

            if y > landscape_height - margin:
                break

        # Render right column
        y = start_y
        for i, component in enumerate(self.right_components):
            # Add spacing between components (except first)
            if i > 0 and not isinstance(component, Space):
                if not isinstance(self.right_components[i - 1], Space):
                    y += theme.spacing.between_components

            # Render component
            height = component.render(draw, right_x, y, right_column_width, fonts)
            y += height

            if y > landscape_height - margin:
                break

        # Rotate for display hardware
        return image.rotate(90, expand=True)
