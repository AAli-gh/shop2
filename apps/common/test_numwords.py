import pytest

from apps.common.numwords import number_to_words


@pytest.mark.parametrize(
    "number, words",
    [
        (0, "صفر"),
        (7, "هفت"),
        (12, "دوازده"),
        (21, "بیست و یک"),
        (105, "صد و پنج"),
        (340, "سیصد و چهل"),
        (1_000, "یک هزار"),
        (1_001, "یک هزار و یک"),
        (250_000, "دویست و پنجاه هزار"),
        (1_250_000, "یک میلیون و دویست و پنجاه هزار"),
        (14_500_000, "چهارده میلیون و پانصد هزار"),
        (2_000_000_000, "دو میلیارد"),
        (-5, "منفی پنج"),
    ],
)
def test_number_to_words(number, words):
    assert number_to_words(number) == words
