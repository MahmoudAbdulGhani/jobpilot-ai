import queue
import threading

from sqlalchemy import delete, event, func, select
from sqlalchemy.orm import Session

from app.models import RefreshToken, User
from app.services import auth_service


def test_concurrent_owner_bootstrap_creates_exactly_one_user(
    test_engine, monkeypatch
):
    with Session(test_engine) as cleanup:
        cleanup.execute(delete(RefreshToken))
        cleanup.execute(delete(User))
        cleanup.commit()

    first_is_inside_lock = threading.Event()
    release_first = threading.Event()
    second_attempted_lock = threading.Event()
    outcomes: queue.Queue[str] = queue.Queue()
    failures: queue.Queue[BaseException] = queue.Queue()
    real_hash_password = auth_service.hash_password

    def gated_hash_password(password: str) -> str:
        if threading.current_thread().name == "bootstrap-first":
            first_is_inside_lock.set()
            assert release_first.wait(timeout=10)
        return real_hash_password(password)

    def observe_lock_attempt(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        if (
            threading.current_thread().name == "bootstrap-second"
            and "pg_advisory_xact_lock" in statement
        ):
            second_attempted_lock.set()

    def bootstrap(email: str) -> None:
        try:
            with Session(test_engine, expire_on_commit=False) as session:
                auth_service.create_first_owner(
                    session, email=email, password="concurrent-owner-password"
                )
            outcomes.put("created")
        except auth_service.OwnerAlreadyExistsError:
            outcomes.put("already-exists")
        except BaseException as exc:
            failures.put(exc)

    monkeypatch.setattr(auth_service, "hash_password", gated_hash_password)
    event.listen(test_engine, "before_cursor_execute", observe_lock_attempt)
    first = threading.Thread(
        target=bootstrap,
        args=("first@jobpilot-test.com",),
        name="bootstrap-first",
    )
    second = threading.Thread(
        target=bootstrap,
        args=("second@jobpilot-test.com",),
        name="bootstrap-second",
    )

    try:
        first.start()
        assert first_is_inside_lock.wait(timeout=10)
        second.start()
        assert second_attempted_lock.wait(timeout=10)
        release_first.set()
        first.join(timeout=15)
        second.join(timeout=15)

        assert not first.is_alive()
        assert not second.is_alive()
        assert failures.empty()
        assert sorted([outcomes.get_nowait(), outcomes.get_nowait()]) == [
            "already-exists",
            "created",
        ]
        with Session(test_engine) as verification:
            assert verification.scalar(select(func.count(User.id))) == 1
    finally:
        release_first.set()
        if first.ident is not None:
            first.join(timeout=15)
        if second.ident is not None:
            second.join(timeout=15)
        event.remove(test_engine, "before_cursor_execute", observe_lock_attempt)
        with Session(test_engine) as cleanup:
            cleanup.execute(delete(RefreshToken))
            cleanup.execute(delete(User))
            cleanup.commit()
