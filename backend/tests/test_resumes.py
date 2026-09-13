import io
import uuid
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.main import create_application
from app.models import Resume, User
from app.services import resume_service, resume_store

TEST_PASSWORD = "resume-test-password"

DOCTYPE_HEADER = b"%PDF-1.4\n"


def pdf_bytes(body: bytes = b"mock resume body") -> bytes:
    return b"%PDF-1.4\n" + body + b"\n%%EOF\n"


CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>QA resume</w:t></w:r></w:p></w:body>"
    "</w:document>"
)


def docx_bytes(
    content_types: str | bytes = CONTENT_TYPES_XML,
    document: str | bytes = DOCUMENT_XML,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as container:
        container.writestr("[Content_Types].xml", content_types)
        container.writestr("word/document.xml", document)
    return buffer.getvalue()


def docx_with_entries(entries: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as container:
        for name, value in entries.items():
            container.writestr(name, value)
    return buffer.getvalue()


@pytest.fixture()
def storage_dir(tmp_path, monkeypatch):
    target = tmp_path / "resumes"
    monkeypatch.setattr(get_settings(), "RESUME_STORAGE_DIR", str(target))
    return target


@pytest.fixture()
def resume_users(db_session):
    first = User(
        email="resume-first@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
    )
    second = User(
        email="resume-second@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)
    return first, second


@pytest.fixture()
def resume_client(db_session):
    app = create_application()

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    return TestClient(app, raise_server_exceptions=False)


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def upload(client, user, filename="cv.pdf", data=None, content_type="application/pdf"):
    data = data if data is not None else pdf_bytes()
    return client.post(
        "/api/resumes",
        headers=auth_headers(user),
        files={"file": (filename, data, content_type)},
    )


def test_all_resume_endpoints_require_authentication(client, resume_users):
    owner, _ = resume_users
    assert (
        client.post(
            "/api/resumes", files={"file": ("cv.pdf", pdf_bytes(), "application/pdf")}
        ).status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert client.get("/api/resumes").status_code == status.HTTP_401_UNAUTHORIZED
    assert (
        client.get(f"/api/resumes/{uuid.uuid4()}/download").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        client.patch(f"/api/resumes/{uuid.uuid4()}", json={"display_name": "x"}).status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        client.delete(f"/api/resumes/{uuid.uuid4()}").status_code
        == status.HTTP_401_UNAUTHORIZED
    )


def test_upload_pdf_persists_metadata_and_file_to_server_prefixed_storage(
    resume_client, resume_users, storage_dir, db_session
):
    owner, _ = resume_users
    response = upload(resume_client, owner, filename="Candidates/CV_2026.pdf")
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["owner_id"] == str(owner.id)
    assert body["original_filename"] == "CV_2026.pdf"
    assert body["display_name"] == "CV_2026.pdf"
    assert body["file_extension"] == "pdf"
    assert body["is_primary"] is False
    assert body["size_bytes"] == len(pdf_bytes())

    resume_id = uuid.UUID(body["id"])
    assert storage_dir.joinpath(str(resume_id)).is_file()
    assert storage_dir.joinpath("CV_2026.pdf").exists() is False
    assert resume_store.file_path(resume_id).read_bytes() == pdf_bytes()

    stored = db_session.scalar(select(Resume).where(Resume.id == resume_id))
    assert stored is not None
    assert stored.original_filename == "CV_2026.pdf"
    assert stored.owner_id == owner.id

    listing = resume_client.get("/api/resumes", headers=auth_headers(owner))
    assert listing.status_code == status.HTTP_200_OK
    assert listing.json()["items"][0]["id"] == body["id"]


def test_upload_docx_accepts_a_valid_container(
    resume_client, resume_users, storage_dir
):
    owner, _ = resume_users
    response = upload(
        resume_client, owner, filename="cv.docx",
        data=docx_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["file_extension"] == "docx"
    assert storage_dir.joinpath(str(body["id"])).read_bytes() == docx_bytes()


def test_upload_rejects_unsupported_extension(resume_client, resume_users):
    owner, _ = resume_users
    response = upload(resume_client, owner, filename="notes.txt", data=b"hello")
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "PDF or DOCX" in response.json()["detail"]

    response = upload(resume_client, owner, filename="cv", data=b"no extension")
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    response = upload(resume_client, owner, filename="cv.PDF", data=pdf_bytes())
    assert response.status_code == status.HTTP_201_CREATED


def test_upload_rejects_oversized_file(resume_client, resume_users, monkeypatch):
    owner, _ = resume_users
    monkeypatch.setattr(get_settings(), "RESUME_MAX_SIZE_MB", 1)
    response = upload(
        resume_client, owner, filename="big.pdf", data=b"x" * (1024 * 1024 + 1024)
    )
    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert "limited to 1 MiB" in response.json()["detail"]


def test_upload_rejects_empty_file(resume_client, resume_users):
    owner, _ = resume_users
    response = upload(resume_client, owner, filename="empty.pdf", data=b"")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"] == "The file is empty."


def test_upload_rejects_malformed_pdf(resume_client, resume_users):
    owner, _ = resume_users
    response = upload(resume_client, owner, filename="text.pdf", data=b"plain text")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"] == "This is not a valid PDF file."

    truncated = upload(resume_client, owner, filename="cut.pdf", data=DOCTYPE_HEADER)
    assert truncated.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_upload_rejects_malformed_docx(resume_client, resume_users):
    owner, _ = resume_users
    not_a_zip = upload(
        resume_client, owner, filename="faked.docx", data=b"not a zip container"
    )
    assert not_a_zip.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert not_a_zip.json()["detail"] == "This is not a valid DOCX file."

    missing_document = io.BytesIO()
    with zipfile.ZipFile(missing_document, "w") as container:
        container.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        container.writestr("word/styles.xml", "<xml/>")
    missing_document = upload(
        resume_client, owner, filename="no-part.docx", data=missing_document.getvalue()
    )
    assert missing_document.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    wrong_position = io.BytesIO()
    with zipfile.ZipFile(wrong_position, "w") as container:
        container.writestr(
            "[Content_Types].xml",
            CONTENT_TYPES_XML.replace("wordprocessingml", "spreadsheetml"),
        )
        container.writestr("word/document.xml", "<w:document/>")
    wrong_position = upload(
        resume_client, owner, filename="spreadsheet.docx", data=wrong_position.getvalue()
    )
    assert wrong_position.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_upload_rejects_docx_over_entry_limit(resume_client, resume_users):
    owner, _ = resume_users
    entries = {
        "[Content_Types].xml": CONTENT_TYPES_XML,
        "word/document.xml": DOCUMENT_XML,
        **{f"custom/item-{index}.xml": "<item/>" for index in range(63)},
    }
    response = upload(
        resume_client, owner, filename="too-many.docx", data=docx_with_entries(entries)
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_upload_rejects_docx_over_total_expanded_limit(resume_client, resume_users):
    owner, _ = resume_users
    response = upload(
        resume_client,
        owner,
        filename="expanded.docx",
        data=docx_with_entries(
            {
                "[Content_Types].xml": CONTENT_TYPES_XML,
                "word/document.xml": DOCUMENT_XML,
                "custom/large.bin": b"x" * (8 * 1024 * 1024),
            }
        ),
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(
    "entries",
    [
        {"word/document.xml": DOCUMENT_XML},
        {"[Content_Types].xml": CONTENT_TYPES_XML},
    ],
)
def test_upload_rejects_docx_missing_required_parts(resume_client, resume_users, entries):
    owner, _ = resume_users
    response = upload(
        resume_client, owner, filename="missing.docx", data=docx_with_entries(entries)
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(
    ("content_types", "document"),
    [
        ("<Types>", DOCUMENT_XML),
        (CONTENT_TYPES_XML, "<w:document>"),
        (
            '<!DOCTYPE Types [<!ENTITY x "value">]><Types>&x;</Types>',
            DOCUMENT_XML,
        ),
        (
            CONTENT_TYPES_XML,
            '<!DOCTYPE document [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">&x;</w:document>',
        ),
        (
            CONTENT_TYPES_XML,
            (
                '<?xml version="1.0" encoding="utf-16"?>'
                '<!DOCTYPE document [<!ENTITY x "value">]>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main">&x;</w:document>'
            ).encode("utf-16"),
        ),
    ],
)
def test_upload_rejects_malformed_or_entity_docx_xml(
    resume_client, resume_users, content_types, document
):
    owner, _ = resume_users
    response = upload(
        resume_client,
        owner,
        filename="malformed.docx",
        data=docx_bytes(content_types=content_types, document=document),
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_submitted_filename_is_metadata_only(resume_client, resume_users, storage_dir):
    owner, _ = resume_users
    response = upload(resume_client, owner, filename="../../secret/../evil.pdf", data=pdf_bytes())
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["original_filename"] == "evil.pdf"

    resume_id = uuid.UUID(body["id"])
    assert storage_dir.joinpath(str(resume_id)).is_file()
    storage_entries = {entry.name for entry in storage_dir.iterdir()}
    assert storage_entries == {str(resume_id)}


def test_upload_without_filename_is_rejected(resume_client, resume_users):
    owner, _ = resume_users
    response = resume_client.post(
        "/api/resumes",
        headers=auth_headers(owner),
        files={"file": ("", pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_download_returns_private_content_without_caching(
    resume_client, resume_users
):
    owner, _ = resume_users
    uploaded = upload(resume_client, owner, filename="My CV.pdf").json()
    response = resume_client.get(
        f"/api/resumes/{uploaded['id']}/download", headers=auth_headers(owner)
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.content == pdf_bytes()
    assert response.headers["content-type"].startswith("application/pdf")
    assert "no-store" in response.headers["cache-control"]
    assert "private" in response.headers["cache-control"]
    assert response.headers.get("pragma") == "no-cache"
    content_disposition = response.headers["content-disposition"]
    assert content_disposition.startswith("attachment; filename")
    assert "My CV.pdf" in content_disposition or "My%20CV.pdf" in content_disposition


def test_download_docx_uses_docx_media_type(resume_client, resume_users):
    owner, _ = resume_users
    uploaded = upload(
        resume_client,
        owner,
        filename="cv.docx",
        data=docx_bytes(),
        content_type="application/octet-stream",
    ).json()
    response = resume_client.get(
        f"/api/resumes/{uploaded['id']}/download", headers=auth_headers(owner)
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_download_missing_resume_is_404(resume_client, resume_users):
    owner, _ = resume_users
    response = resume_client.get(
        f"/api/resumes/{uuid.uuid4()}/download", headers=auth_headers(owner)
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Resume not found"}


def test_cross_user_download_is_indistinguishable_from_missing(
    resume_client, resume_users
):
    first, second = resume_users
    uploaded = upload(resume_client, first, filename="private.pdf").json()
    denied = resume_client.get(
        f"/api/resumes/{uploaded['id']}/download", headers=auth_headers(second)
    )
    missing = resume_client.get(
        f"/api/resumes/{uuid.uuid4()}/download", headers=auth_headers(second)
    )
    assert denied.status_code == status.HTTP_404_NOT_FOUND
    assert denied.json() == missing.json()


def test_cross_user_patch_and_delete_are_denied(resume_client, resume_users):
    first, second = resume_users
    uploaded = upload(resume_client, first, filename="private.pdf").json()
    assert (
        resume_client.patch(
            f"/api/resumes/{uploaded['id']}",
            json={"display_name": "stolen"},
            headers=auth_headers(second),
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert (
        resume_client.delete(
            f"/api/resumes/{uploaded['id']}", headers=auth_headers(second)
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )
    listing = resume_client.get("/api/resumes", headers=auth_headers(second))
    assert listing.json()["items"] == []


def test_rename_sets_display_name(resume_client, resume_users):
    owner, _ = resume_users
    uploaded = upload(resume_client, owner, filename="draft_cv.pdf").json()
    response = resume_client.patch(
        f"/api/resumes/{uploaded['id']}",
        json={"display_name": "  Main CV for 2026  "},
        headers=auth_headers(owner),
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["display_name"] == "Main CV for 2026"
    assert body["original_filename"] == "draft_cv.pdf"


def test_rename_validation(resume_client, resume_users):
    owner, _ = resume_users
    uploaded = upload(resume_client, owner).json()
    url = f"/api/resumes/{uploaded['id']}"
    for invalid in ({"display_name": "   "}, {"display_name": ""}):
        response = resume_client.patch(
            url, json=invalid, headers=auth_headers(owner)
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    too_long = resume_client.patch(
        url, json={"display_name": "x" * 256}, headers=auth_headers(owner)
    )
    assert too_long.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    extra = resume_client.patch(
        url, json={"display_name": "CV", "owner_id": str(owner.id)}, headers=auth_headers(owner)
    )
    assert extra.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_primary_selection_is_single_and_transfers(
    resume_client, resume_users, db_session
):
    owner, _ = resume_users
    first = upload(resume_client, owner, filename="one.pdf").json()
    second = upload(resume_client, owner, filename="two.pdf").json()

    response = resume_client.patch(
        f"/api/resumes/{first['id']}",
        json={"is_primary": True},
        headers=auth_headers(owner),
    )
    assert response.json()["is_primary"] is True

    promoted = resume_client.patch(
        f"/api/resumes/{second['id']}",
        json={"is_primary": True},
        headers=auth_headers(owner),
    )
    assert promoted.status_code == status.HTTP_200_OK
    assert promoted.json()["is_primary"] is True

    demoted = resume_client.get("/api/resumes", headers=auth_headers(owner)).json()
    by_id = {item["id"]: item for item in demoted["items"]}
    assert by_id[first["id"]]["is_primary"] is False
    assert by_id[second["id"]]["is_primary"] is True

    primary_rows = list(
        db_session.scalars(select(Resume).where(Resume.is_primary.is_(True)))
    )
    assert len(primary_rows) == 1
    assert primary_rows[0].id == uuid.UUID(second["id"])

    cleared = resume_client.patch(
        f"/api/resumes/{second['id']}",
        json={"is_primary": False},
        headers=auth_headers(owner),
    )
    assert cleared.json()["is_primary"] is False
    remaining = list(
        db_session.scalars(select(Resume).where(Resume.is_primary.is_(True)))
    )
    assert remaining == []


def test_database_rejects_two_primary_resumes_for_same_owner(db_session, resume_users):
    first, _ = resume_users
    db_session.add_all(
        [
            Resume(owner_id=first.id, original_filename="a.pdf", display_name="a.pdf",
                   file_extension="pdf", size_bytes=1, is_primary=True),
            Resume(owner_id=first.id, original_filename="b.pdf", display_name="b.pdf",
                   file_extension="pdf", size_bytes=1, is_primary=True),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_delete_removes_row_and_file(resume_client, resume_users, storage_dir, db_session):
    owner, _ = resume_users
    uploaded = upload(resume_client, owner, filename="gone.pdf").json()
    resume_id = uuid.UUID(uploaded["id"])
    assert storage_dir.joinpath(str(resume_id)).is_file()

    response = resume_client.delete(
        f"/api/resumes/{resume_id}", headers=auth_headers(owner)
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert storage_dir.joinpath(str(resume_id)).exists() is False
    assert db_session.scalar(select(Resume).where(Resume.id == resume_id)) is None
    assert resume_client.get("/api/resumes", headers=auth_headers(owner)).json()["items"] == []
    assert (
        resume_client.get(
            f"/api/resumes/{resume_id}/download", headers=auth_headers(owner)
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert (
        resume_client.delete(
            f"/api/resumes/{resume_id}", headers=auth_headers(owner)
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )


def test_storage_failure_leaves_no_database_row(
    resume_client, resume_users, monkeypatch, db_session
):
    owner, _ = resume_users

    def failing_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.resume_service.resume_store.write_bytes", failing_write)
    response = upload(resume_client, owner, filename="fail.pdf")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert db_session.scalar(
        select(Resume).where(Resume.owner_id == owner.id)
    ) is None
    assert resume_client.get("/api/resumes", headers=auth_headers(owner)).json()["items"] == []


def test_resume_survives_engine_restart(storage_dir, test_engine):
    from app.core.security import hash_password
    from sqlalchemy.orm import Session as sa_session

    owner_email = f"persist-{uuid.uuid4()}@jobpilot-test.com"
    with sa_session(test_engine) as saving_session:
        committed_owner = User(email=owner_email, password_hash=hash_password(TEST_PASSWORD))
        saving_session.add(committed_owner)
        saving_session.commit()
        owner_id = committed_owner.id

        resume_store.ensure_storage_dir()
        created = resume_service.create_resume(
            saving_session,
            owner_id=owner_id,
            original_filename="lasting.pdf",
            display_name="lasting.pdf",
            file_extension="pdf",
            size_bytes=len(pdf_bytes()),
            data=pdf_bytes(),
        )
        resume_id = created.id

    reopened_engine = create_engine(
        test_engine.url.render_as_string(hide_password=False)
    )
    try:
        with sa_session(reopened_engine) as fresh_session:
            persisted = fresh_session.scalar(select(Resume).where(Resume.id == resume_id))
            assert persisted is not None
            assert persisted.owner_id == owner_id
            assert persisted.original_filename == "lasting.pdf"
            assert persisted.size_bytes == len(pdf_bytes())
    finally:
        reopened_engine.dispose()

    with sa_session(test_engine) as cleanup_session:
        retained = cleanup_session.scalar(select(User).where(User.id == owner_id))
        if retained is not None:
            cleanup_session.delete(retained)
            cleanup_session.commit()

    assert storage_dir.joinpath(str(resume_id)).read_bytes() == pdf_bytes()


def test_e2e_bootstrap_and_cleanup_are_guarded_outside_test_database(client):
    payload = {"email": "guarded@jobpilot-test.com", "password": "password-123"}
    assert (
        client.post("/api/e2e/bootstrap", json=payload).status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert (
        client.post(
            "/api/e2e/cleanup",
            json={"email": "guarded@jobpilot-test.com", "password": "password-123"},
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )


def test_e2e_bootstrap_creates_idempotent_disposable_users(
    resume_client, db_session, monkeypatch
):
    fake_settings = SimpleNamespace(
        database_url="postgresql+psycopg://u:p@host:5433/jobpilot_test",
        POSTGRES_TEST_DB="jobpilot_test",
        E2E_TEST_MODE=True,
    )
    monkeypatch.setattr("app.api.routes.e2e.get_settings", lambda: fake_settings)
    payload = {
        "email": "e2e-run@jobpilot-test.com",
        "password": "disposable-password",
    }
    first = resume_client.post("/api/e2e/bootstrap", json=payload)
    assert first.status_code == status.HTTP_200_OK
    second = resume_client.post("/api/e2e/bootstrap", json=payload)
    assert second.status_code == status.HTTP_200_OK
    assert second.json()["user_id"] == first.json()["user_id"]
    stored = db_session.scalar(select(User).where(User.email == payload["email"]))
    assert stored is not None

    cleaned = resume_client.post("/api/e2e/cleanup", json=payload)
    assert cleaned.status_code == status.HTTP_200_OK
    assert cleaned.json() == {"deleted": True}
    assert db_session.scalar(select(User).where(User.email == payload["email"])) is None
    again = resume_client.post("/api/e2e/cleanup", json=payload)
    assert again.json() == {"deleted": False}


def test_e2e_cleanup_removes_resumes_and_their_files(
    resume_client, db_session, storage_dir, monkeypatch
):
    fake_settings = SimpleNamespace(
        database_url="postgresql+psycopg://u:p@host:5433/jobpilot_test",
        POSTGRES_TEST_DB="jobpilot_test",
        E2E_TEST_MODE=True,
    )
    monkeypatch.setattr("app.api.routes.e2e.get_settings", lambda: fake_settings)
    credentials = {
        "email": "cleanup-run@jobpilot-test.com",
        "password": "disposable-password",
    }
    created = resume_client.post(
        "/api/e2e/bootstrap",
        json=credentials,
    ).json()
    user = db_session.scalar(select(User).where(User.email == created["email"]))

    uploaded = upload(resume_client, user, filename="to-remove.pdf").json()
    resume_id = uuid.UUID(uploaded["id"])
    assert storage_dir.joinpath(str(resume_id)).is_file()

    cleaned = resume_client.post(
        "/api/e2e/cleanup", json=credentials
    )
    assert cleaned.json() == {"deleted": True}
    assert storage_dir.joinpath(str(resume_id)).exists() is False
    assert db_session.scalar(select(Resume).where(Resume.id == resume_id)) is None


@pytest.mark.parametrize(
    ("enabled", "database_url"),
    [
        (False, "postgresql+psycopg://u:p@host:5433/jobpilot_test"),
        (True, "postgresql+psycopg://u:p@host:5433/jobpilot"),
    ],
)
def test_e2e_endpoints_require_mode_and_test_database(
    resume_client, monkeypatch, enabled, database_url
):
    fake_settings = SimpleNamespace(
        database_url=database_url,
        POSTGRES_TEST_DB="jobpilot_test",
        E2E_TEST_MODE=enabled,
    )
    monkeypatch.setattr("app.api.routes.e2e.get_settings", lambda: fake_settings)
    credentials = {"email": "double-guard@jobpilot-test.com", "password": "password-123"}
    assert resume_client.post("/api/e2e/bootstrap", json=credentials).status_code == 404
    assert resume_client.post("/api/e2e/cleanup", json=credentials).status_code == 404


def test_e2e_cleanup_cannot_remove_another_runs_user(
    resume_client, db_session, monkeypatch
):
    fake_settings = SimpleNamespace(
        database_url="postgresql+psycopg://u:p@host:5433/jobpilot_test",
        POSTGRES_TEST_DB="jobpilot_test",
        E2E_TEST_MODE=True,
    )
    monkeypatch.setattr("app.api.routes.e2e.get_settings", lambda: fake_settings)
    owner = {"email": "owned-run@jobpilot-test.com", "password": "owner-password"}
    assert resume_client.post("/api/e2e/bootstrap", json=owner).status_code == 200

    denied = resume_client.post(
        "/api/e2e/cleanup",
        json={"email": owner["email"], "password": "different-run-password"},
    )
    assert denied.json() == {"deleted": False}
    assert db_session.scalar(select(User).where(User.email == owner["email"])) is not None
