import pytest


class DummyUploadFile:
    def __init__(self, filename: str, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type


@pytest.fixture(scope="module")
def validate_file_type_func():
    pytest.importorskip("fastapi")
    from app.utils.image_validation import validate_file_type

    return validate_file_type


def _upload(filename: str, ctype: str) -> DummyUploadFile:
    return DummyUploadFile(filename=filename, content_type=ctype)


@pytest.mark.parametrize(
    "name,ctype", [("a.jpg", "image/jpeg"), ("b.png", "image/png")]
)
def test_validate_file_type_valid(
    name: str, ctype: str, validate_file_type_func
) -> None:
    validate_file_type_func(_upload(name, ctype))


def test_validate_file_type_invalid(validate_file_type_func) -> None:
    with pytest.raises(Exception):
        validate_file_type_func(_upload("a.gif", "image/gif"))
