import pytest
pytest.importorskip("fastapi")

import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.utils.image_validation import validate_file_type


def _upload(filename: str, ctype: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(b"x"), filename=filename, headers=Headers({"content-type": ctype}))


@pytest.mark.parametrize("name,ctype", [("a.jpg", "image/jpeg"), ("b.png", "image/png")])
def test_validate_file_type_valid(name: str, ctype: str) -> None:
    validate_file_type(_upload(name, ctype))


def test_validate_file_type_invalid() -> None:
    with pytest.raises(Exception):
        validate_file_type(_upload("a.gif", "image/gif"))
