"""Global logical-delete filtering.

The listener is registered once, at import time, so **every** ORM SELECT is
filtered no matter which code created the session. A filter that only applies
when each call site remembers to install it is a data-leak waiting to happen.

Opting out is explicit and per session or per statement:

    include_deleted(session)
    await session.execute(select(User), execution_options={"include_deleted": True})
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.core.constants import DelFlagEnum
from app.db.base import SoftDeleteMixin

#: Execution option / session-info key that disables the filter.
INCLUDE_DELETED = "include_deleted"


def _soft_delete_listener(state: ORMExecuteState) -> None:
    # Column and relationship loads reuse the parent statement's criteria already;
    # re-applying here would emit duplicate WHERE fragments.
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    if state.execution_options.get(INCLUDE_DELETED) or state.session.info.get(INCLUDE_DELETED):
        return

    state.statement = state.statement.options(
        with_loader_criteria(
            SoftDeleteMixin,
            lambda cls: cls.del_flag == DelFlagEnum.EXISTS,
            include_aliases=True,
        )
    )


def install_soft_delete_filter(session: Any = None) -> None:
    """Guarantee the global filter is attached. Idempotent.

    The listener is already registered when this module is imported; this function
    exists so call sites (the `get_db` dependency and the test session fixture) can
    state the requirement explicitly. The `session` argument is accepted and unused
    because the filter is global by design rather than per session.
    """
    if is_soft_delete_filter_installed():
        return
    event.listen(Session, "do_orm_execute", _soft_delete_listener)


def is_soft_delete_filter_installed() -> bool:
    """True when the global filter listener is attached to `Session`."""
    return event.contains(Session, "do_orm_execute", _soft_delete_listener)


def include_deleted(session: Any) -> None:
    """Escape hatch: this session now sees logically deleted rows too."""
    session.info[INCLUDE_DELETED] = True


# Active from import onward: see the module docstring.
install_soft_delete_filter()
